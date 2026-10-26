"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { Check, Loader2, Sparkles, Upload, X } from "lucide-react"
import {
  BODY_ROLE, FACE_ROLE, categoryOf, guessRole, suggestRole, uploadOne,
  type StudioPresets, type Suggestion,
} from "./studio-lib"

// 기존 이미지 가져오기 — 여러 장 끌어다 놓기 → 역할 자동 채움(파일 이름이 역할 이름이면 그대로, 아니면
// 비전 AI 추천) → 대표는 틀린 것만 고친다 → 한 장씩 순서대로 등록. "기준 이미지 아님"은 기본 제외.

interface Staged {
  key: string
  file: File
  preview: string
  role: string
  custom: boolean
  include: boolean
  hint: { by: "file" | "ai" | "none"; text: string; warn?: boolean }
  state: "analyzing" | "idle" | "uploading" | "done" | "error"
  error?: string
}

const CUSTOM = "__custom__"
const KIND_KO: Record<string, string> = { face: "얼굴", body: "체형", hair: "헤어", pose: "포즈" }

export function ImportPanel({ characterId, roleRe, presets, existing, catLabel, onDone }: {
  characterId: string
  roleRe: RegExp
  presets: StudioPresets
  existing: string[]
  catLabel: Record<string, string>
  onDone: () => Promise<unknown>
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [items, setItems] = useState<Staged[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [confirm, setConfirm] = useState(true)
  const [running, setRunning] = useState(false)
  const itemsRef = useRef(items)
  useEffect(() => {
    itemsRef.current = items
  }, [items])
  useEffect(() => () => itemsRef.current.forEach((it) => URL.revokeObjectURL(it.preview)), [])

  // 드롭다운 = 얼굴·체형 + 헤어·포즈 프리셋 + 이미 있는 역할 + 지금 들어온 역할(분류별 묶음).
  const options = useMemo(() => {
    const all = new Set<string>([FACE_ROLE, BODY_ROLE, ...presets.hair.map((h) => h.role), ...presets.pose.map((p) => p.role), ...existing])
    items.forEach((it) => it.role && roleRe.test(it.role) && all.add(it.role))
    const groups: Record<string, string[]> = {}
    ;[...all].sort().forEach((r) => (groups[categoryOf(r)] ??= []).push(r))
    return groups
  }, [presets, existing, items, roleRe])

  function update(key: string, patch: Partial<Staged>) {
    setItems((prev) => prev.map((it) => (it.key === key ? { ...it, ...patch } : it)))
  }

  async function analyze(list: Staged[]) {
    // AI 추천은 2장씩 병렬 — 대표가 기다리는 시간을 줄이되 백엔드에 몰리지 않게.
    const queue = [...list]
    const worker = async () => {
      for (let it = queue.shift(); it; it = queue.shift()) {
        try {
          const s: Suggestion = await suggestRole(characterId, it.file)
          const pct = Math.round(s.confidence * 100)
          if (s.kind === "not_reference") {
            update(it.key, { state: "idle", include: false, role: "", hint: { by: "ai", text: `기준 이미지 아님 — ${s.reason || "착장·스크린샷 등"}`, warn: true } })
          } else {
            update(it.key, {
              state: "idle", role: s.role, include: true,
              hint: { by: "ai", text: `AI 추천 · ${KIND_KO[s.kind] ?? s.kind} ${pct}%${s.reason ? ` · ${s.reason}` : ""}`, warn: !s.role || pct < 60 },
            })
          }
        } catch (e) {
          update(it.key, { state: "idle", hint: { by: "none", text: `AI 추천 실패 — 직접 골라 주세요 (${e instanceof Error ? e.message : "오류"})`, warn: true } })
        }
      }
    }
    await Promise.all([worker(), worker()])
  }

  function add(files: FileList | File[]) {
    const list = Array.from(files)
    const ok = list.filter((f) => /\.(png|jpe?g|webp)$/i.test(f.name))
    if (ok.length < list.length) toast.error(`png·jpg·webp 이 아닌 ${list.length - ok.length}개는 뺐어요`)
    const staged: Staged[] = ok.map((file, i) => {
      const role = guessRole(file.name, roleRe)
      return {
        key: `${Date.now()}-${i}-${file.name}`,
        file,
        preview: URL.createObjectURL(file),
        role,
        custom: false,
        include: true,
        hint: role ? { by: "file", text: "파일 이름으로 인식" } : { by: "ai", text: "AI가 보는 중…" },
        state: role ? "idle" : "analyzing",
      }
    })
    setItems((prev) => [...prev, ...staged])
    const toAnalyze = staged.filter((s) => s.state === "analyzing")
    if (toAnalyze.length) void analyze(toAnalyze)
  }

  function remove(key: string) {
    setItems((prev) => {
      const it = prev.find((x) => x.key === key)
      if (it) URL.revokeObjectURL(it.preview)
      return prev.filter((x) => x.key !== key)
    })
  }

  const pending = items.filter((it) => it.include && (it.state === "idle" || it.state === "error"))
  const analyzing = items.some((it) => it.state === "analyzing")
  const invalid = pending.filter((it) => !roleRe.test(it.role))
  const roleCount = pending.reduce<Record<string, number>>((m, it) => ((m[it.role] = (m[it.role] ?? 0) + 1), m), {})
  const dupes = Object.keys(roleCount).filter((r) => r && roleCount[r] > 1)

  async function submit() {
    if (invalid.length) {
      toast.error(`역할이 비었거나 규칙에 안 맞는 이미지가 ${invalid.length}장 있어요`)
      return
    }
    setRunning(true)
    let okCount = 0
    // 한 장씩 순서대로(백엔드 ffmpeg·R2 부하, Vercel 동시 요청 회피).
    for (const it of pending) {
      update(it.key, { state: "uploading", error: undefined })
      try {
        await uploadOne(characterId, it.file, it.role, confirm)
        update(it.key, { state: "done" })
        okCount += 1
      } catch (e) {
        update(it.key, { state: "error", error: e instanceof Error ? e.message : "업로드 실패" })
      }
    }
    setRunning(false)
    const failed = pending.length - okCount
    if (okCount) toast.success(`${okCount}장 등록${confirm ? "(확정)" : "(후보)"}`)
    if (failed) toast.error(`${failed}장 실패 — 사유를 확인해 주세요`)
    await onDone()
  }

  function clearDone() {
    setItems((prev) => {
      prev.filter((x) => x.state === "done").forEach((x) => URL.revokeObjectURL(x.preview))
      return prev.filter((x) => x.state !== "done")
    })
  }

  return (
    <div className="flex min-w-0 flex-col gap-3 rounded-xl border border-border bg-card p-3">
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1 basis-64">
          <h2 className="text-sm font-semibold text-foreground">기존 이미지 가져오기</h2>
          <p className="text-[11px] text-muted-foreground">
            여러 장을 한 번에 끌어다 놓으세요. AI가 이미지를 보고 역할을 채워 줘요 — 틀린 것만 고치면 돼요.
          </p>
        </div>
        <label className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
          <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} disabled={running} />
          바로 확정
        </label>
      </div>

      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          if (e.dataTransfer.files?.length) add(e.dataTransfer.files)
        }}
        className={`flex min-h-[88px] cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border border-dashed px-3 py-4 text-center text-xs transition-colors ${
          dragOver ? "border-primary/60 bg-primary/5 text-foreground" : "border-border text-muted-foreground hover:border-primary/40"
        }`}
      >
        <Upload className="h-5 w-5" />
        <span>이미지를 여기로 끌어다 놓거나 눌러서 고르세요 (png·jpg·webp, 여러 장)</span>
        <span className="text-[11px]">얼굴: 짧은 변 768px 이상 · 그 외: 긴 변 1024px 이상 · 3.8MB 넘으면 자동으로 줄여 보내요</span>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept="image/png,image/jpeg,image/webp"
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) add(e.target.files)
            e.target.value = ""
          }}
        />
      </div>

      {items.length > 0 && (
        <>
          <div className="grid min-w-0 gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {items.map((it) => {
              const editable = it.state === "idle" || it.state === "error"
              const bad = it.include && editable && !roleRe.test(it.role)
              const inOptions = Object.values(options).some((g) => g.includes(it.role))
              const selectValue = it.custom || (it.role && !inOptions) ? CUSTOM : it.role
              return (
                <div key={it.key} className={`flex min-w-0 gap-2 rounded-lg border border-border bg-background p-2 ${it.include ? "" : "opacity-60"}`}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={it.preview} alt={it.file.name} className="h-20 w-16 shrink-0 rounded-md bg-secondary/30 object-cover" />
                  <div className="flex min-w-0 flex-1 flex-col gap-1">
                    <div className="flex min-w-0 items-center gap-1">
                      <p className="min-w-0 truncate text-[11px] text-muted-foreground" title={it.file.name}>{it.file.name}</p>
                      {it.state !== "uploading" && (
                        <button onClick={() => remove(it.key)} disabled={running} aria-label="빼기" className="ml-auto shrink-0 text-muted-foreground hover:text-foreground disabled:opacity-50">
                          <X className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                    <select
                      value={selectValue}
                      disabled={running || !editable || !it.include}
                      onChange={(e) =>
                        e.target.value === CUSTOM
                          ? update(it.key, { custom: true })
                          : update(it.key, { role: e.target.value, custom: false })
                      }
                      className={`w-full min-w-0 rounded-md border bg-background px-1.5 py-1 text-xs text-foreground ${bad ? "border-amber-500/50" : "border-border"}`}
                    >
                      <option value="">{it.state === "analyzing" ? "AI가 보는 중…" : "역할 선택…"}</option>
                      {Object.entries(options).map(([cat, roles]) => (
                        <optgroup key={cat} label={catLabel[cat] ?? cat}>
                          {roles.map((r) => (
                            <option key={r} value={r}>{r}</option>
                          ))}
                        </optgroup>
                      ))}
                      <option value={CUSTOM}>직접 입력…</option>
                    </select>
                    {selectValue === CUSTOM && it.include && (
                      <input
                        value={it.role}
                        disabled={running || !editable}
                        onChange={(e) => update(it.key, { role: e.target.value.trim().toLowerCase() })}
                        placeholder="예: hair_12_bob"
                        className={`w-full min-w-0 rounded-md border bg-background px-1.5 py-1 text-xs text-foreground ${bad ? "border-amber-500/50" : "border-border"}`}
                      />
                    )}
                    <div className="flex min-w-0 items-center gap-1.5 text-[11px]">
                      {editable && (
                        <label className="flex shrink-0 items-center gap-1 text-muted-foreground">
                          <input type="checkbox" checked={it.include} disabled={running} onChange={(e) => update(it.key, { include: e.target.checked })} />
                          포함
                        </label>
                      )}
                      <span className="min-w-0 break-words">
                        {it.state === "analyzing" ? (
                          <span className="flex items-center gap-1 text-primary"><Loader2 className="h-3 w-3 animate-spin" /> AI가 보는 중</span>
                        ) : it.state === "uploading" ? (
                          <span className="flex items-center gap-1 text-primary"><Loader2 className="h-3 w-3 animate-spin" /> 올리는 중</span>
                        ) : it.state === "done" ? (
                          <span className="flex items-center gap-1 text-emerald-400"><Check className="h-3 w-3" /> 등록됨</span>
                        ) : it.state === "error" ? (
                          <span className="text-red-400">{it.error}</span>
                        ) : bad ? (
                          <span className="text-amber-400">{it.role ? "소문자·숫자·_ 2~40자" : "역할을 골라 주세요"}</span>
                        ) : it.include && dupes.includes(it.role) ? (
                          <span className="text-amber-400">같은 역할이 여러 장 — 마지막 장이 확정돼요</span>
                        ) : (
                          <span className={`inline-flex items-center gap-1 ${it.hint.warn ? "text-amber-400" : "text-muted-foreground"}`}>
                            {it.hint.by === "ai" && <Sparkles className="h-3 w-3 shrink-0" />}
                            {it.hint.text}
                          </span>
                        )}
                      </span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            {items.some((it) => it.state === "done") && (
              <button onClick={clearDone} disabled={running} className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground disabled:opacity-50">
                등록된 항목 지우기
              </button>
            )}
            <button
              onClick={submit}
              disabled={running || analyzing || pending.length === 0}
              className="flex min-h-[36px] items-center gap-1.5 rounded-lg bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {running || analyzing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
              {analyzing ? "AI 추천 중…" : `${pending.length}장 등록`}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
