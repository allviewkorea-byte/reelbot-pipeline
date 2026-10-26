"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { Check, Info, Loader2, Sparkles, Upload, X } from "lucide-react"
import {
  BODY_ROLE, FACE_ROLE, categoryOf, guessRole, suggestRole, uploadOne,
  type StudioPresets, type Suggestion,
} from "./studio-lib"

// 기존 이미지 가져오기 — 여러 장 끌어다 놓기 → 모든 이미지를 비전 AI 가 보고 역할을 채운다 → 대표는 틀린
// 것만 고친다 → 한 장씩 순서대로 등록.
// 채우는 규칙: AI 우선. 단 파일명이 01_face/02_body 면 파일명 우선(AI 얼굴 오판 보정).
// AI 가 "기준 이미지 아님"이면 항상 제외.
// AI 실패 → 파일명으로 채우고 빨간 한 줄. 카드엔 손댈 것만 태그(역할 선택 필요·같은 역할 여러 장),
// AI 이유·파일명과 다름·파일명 우선은 "이유" 툴팁/클릭에만.

interface Staged {
  key: string
  file: File
  preview: string
  role: string
  fileRole: string
  custom: boolean
  include: boolean
  ai: AiNote
  state: "analyzing" | "idle" | "uploading" | "done" | "error"
  error?: string
}

// AI 추천 결과(화면 배지용). status: ok 정상 / differs 파일명과 다름 / kept 파일명 우선(AI 는 다르게 봄)
// / pick 종류만 앎(목록에서 선택) / not_ref 기준 이미지 아님 / failed 호출 실패.
interface AiNote {
  status: "pending" | "ok" | "differs" | "kept" | "pick" | "not_ref" | "failed"
  kind?: string
  pct?: number
  reason?: string
  aiRole?: string
  error?: string
}

const CUSTOM = "__custom__"
// 파일명이 이 역할이면 파일명 우선(실사용에서 01_face 를 hair_01_straight 로 오판).
const FILE_FIRST = new Set([FACE_ROLE, BODY_ROLE])
const TAG = "inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium leading-none"
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
  const [openReason, setOpenReason] = useState<string | null>(null)
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
        const fileRole = it.fileRole
        try {
          const s: Suggestion = await suggestRole(characterId, it.file)
          const base = { kind: s.kind, pct: Math.round(s.confidence * 100), reason: s.reason, aiRole: s.role }
          if (s.kind === "not_reference") {
            update(it.key, { state: "idle", include: false, role: "", ai: { ...base, status: "not_ref" } })
          } else if (FILE_FIRST.has(fileRole)) {
            update(it.key, { state: "idle", include: true, role: fileRole, ai: { ...base, status: s.role === fileRole ? "ok" : "kept" } })
          } else if (!s.role) {
            update(it.key, { state: "idle", include: true, role: fileRole, ai: { ...base, status: "pick" } })
          } else {
            const differs = !!fileRole && fileRole !== s.role
            update(it.key, { state: "idle", include: true, role: s.role, ai: { ...base, status: differs ? "differs" : "ok" } })
          }
        } catch (e) {
          const msg = (e instanceof Error ? e.message : "오류").replace(/^AI 역할 추천 실패:\s*/, "")
          update(it.key, { state: "idle", role: fileRole, ai: { status: "failed", error: msg } })
        }
      }
    }
    await Promise.all([worker(), worker()])
  }

  function add(files: FileList | File[]) {
    const list = Array.from(files)
    const ok = list.filter((f) => /\.(png|jpe?g|webp)$/i.test(f.name))
    if (ok.length < list.length) toast.error(`png·jpg·webp 이 아닌 ${list.length - ok.length}개는 뺐어요`)
    // 모든 이미지를 AI 가 본다(파일 이름은 참고·실패 시 대체용).
    const staged: Staged[] = ok.map((file, i) => {
      const fileRole = guessRole(file.name, roleRe)
      return {
        key: `${Date.now()}-${i}-${file.name}`,
        file,
        preview: URL.createObjectURL(file),
        role: fileRole,
        fileRole,
        custom: false,
        include: true,
        ai: { status: "pending" },
        state: "analyzing",
      }
    })
    setItems((prev) => [...prev, ...staged])
    if (staged.length) void analyze(staged)
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
                    <StatusRow
                      it={it}
                      editable={editable}
                      running={running}
                      bad={bad}
                      dupe={it.include && editable && dupes.includes(it.role)}
                      reasonOpen={openReason === it.key}
                      onToggleReason={() => setOpenReason((k) => (k === it.key ? null : it.key))}
                      onInclude={(v) => update(it.key, { include: v })}
                    />
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

/** 카드 아래 한 줄 — [포함] [AI 배지] [손댈 것 태그: 역할 선택 필요·같은 역할 여러 장] [이유].
 * 실패는 빨간 한 줄. 파일명과 다름·파일명 우선 같은 참고 정보는 이유 툴팁·펼침에만. */
function StatusRow({ it, editable, running, bad, dupe, reasonOpen, onToggleReason, onInclude }: {
  it: Staged
  editable: boolean
  running: boolean
  bad: boolean
  dupe: boolean
  reasonOpen: boolean
  onToggleReason: () => void
  onInclude: (v: boolean) => void
}) {
  const ai = it.ai
  const kind = ai.kind ? KIND_KO[ai.kind] : null
  // 참고 정보(대표가 손댈 필요 없음)는 카드에 태그로 두지 않고 ⓘ 이유 툴팁·펼침에만.
  const details = [
    ai.reason?.trim(),
    ai.status === "differs" ? `파일명과 다름 — 파일명: ${it.fileRole}` : "",
    ai.status === "kept" ? `파일명(${it.fileRole}) 우선 — AI는 ${ai.aiRole || kind || "다르게"} 로 봤어요` : "",
    ai.status === "pick" ? `AI가 ${kind ?? "종류"}로 봤지만 목록에서 고르지 못했어요` : "",
  ].filter((d): d is string => !!d)

  if (it.state === "analyzing")
    return <p className="flex items-center gap-1 text-[11px] text-primary"><Loader2 className="h-3 w-3 animate-spin" /> AI가 보는 중</p>
  if (it.state === "uploading")
    return <p className="flex items-center gap-1 text-[11px] text-primary"><Loader2 className="h-3 w-3 animate-spin" /> 올리는 중</p>
  if (it.state === "done")
    return <p className="flex items-center gap-1 text-[11px] text-emerald-400"><Check className="h-3 w-3" /> 등록됨</p>

  return (
    <div className="flex min-w-0 flex-col gap-1">
      <div className="flex min-w-0 flex-wrap items-center gap-1">
        {editable && (
          <label className="mr-0.5 flex shrink-0 items-center gap-1 text-[11px] text-muted-foreground">
            <input type="checkbox" checked={it.include} disabled={running} onChange={(e) => onInclude(e.target.checked)} />
            포함
          </label>
        )}
        {ai.status === "failed" ? (
          <span className="min-w-0 truncate text-[11px] text-red-400" title={ai.error}>
            AI 추천 실패{it.fileRole ? " · 파일명으로 채움" : ""} · {ai.error}
          </span>
        ) : ai.status === "not_ref" ? (
          <span className={`${TAG} bg-secondary text-muted-foreground`}>기준 이미지 아님</span>
        ) : (
          kind && ai.status !== "kept" && (
            <span className={`${TAG} bg-secondary/60 text-muted-foreground`} title={ai.aiRole || undefined}>
              <Sparkles className="h-2.5 w-2.5" /> AI {kind}{ai.pct !== undefined ? ` · ${ai.pct}%` : ""}
            </span>
          )
        )}
        {bad && <span className={`${TAG} bg-amber-500/10 text-amber-400`}>역할 선택 필요</span>}
        {dupe && <span className={`${TAG} bg-amber-500/10 text-amber-400`} title="마지막 장이 확정돼요">같은 역할 여러 장</span>}
        {details.length > 0 && (
          <button
            type="button"
            onClick={onToggleReason}
            title={details.join("\n")}
            aria-expanded={reasonOpen}
            className="ml-auto flex shrink-0 items-center gap-0.5 text-[10px] text-muted-foreground hover:text-foreground"
          >
            <Info className="h-3 w-3" /> 이유
          </button>
        )}
      </div>
      {reasonOpen && details.map((d) => <p key={d} className="break-words text-[11px] text-muted-foreground">{d}</p>)}
      {it.state === "error" && <p className="min-w-0 truncate text-[11px] text-red-400" title={it.error}>{it.error}</p>}
    </div>
  )
}
