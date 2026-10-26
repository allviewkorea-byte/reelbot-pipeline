"use client"

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"
import { Check, CheckCircle2, ImageIcon, Loader2, Trash2, Upload, UserRound, X } from "lucide-react"
import { prepareFile } from "@/components/shorts/FamilyCastPanel"

// 캐릭터 스튜디오(채널 공통, A0-2) — 기존 이미지 가져오기(여러 장 끌어다 놓기 → 이미지마다 역할 지정 → 등록),
// 역할별 확정 1장 + 후보 목록(확정 바꾸기·버리기), 준비 상태(01_face·02_body 확정). 생성(후보 뽑기)은 A0-3.
// 백엔드: /studio/*(character_studio.py). 쇼츠 hero(/shorts/cast)·백곰(/cast)과 분리.

interface Ref {
  id: number
  role: string
  status: "candidate" | "confirmed" | "discarded"
  source: "upload" | "generated"
  url: string
  w: number | null
  h: number | null
  created_at: string
}
interface RoleSlot { role: string; category: string; confirmed: Ref | null; candidates: Ref[] }
interface Character { id: string; name: string; channel_id: string | null }
interface View { character: Character; roles: RoleSlot[]; required: string[]; missing_required: string[]; ready: boolean }
interface Presets { categories: { key: string; label: string; min: string }[]; required: string[]; pattern: string; examples: string[] }

interface Staged {
  key: string
  file: File
  preview: string
  role: string
  custom: boolean
  state: "idle" | "uploading" | "done" | "error"
  error?: string
}

const DEFAULT_CHARACTER = "chaei"
const ROLE_FALLBACK = "^[a-z0-9][a-z0-9_]{1,39}$"
const REQUIRED_KO: Record<string, string> = { "01_face": "얼굴", "02_body": "체형" }
const CUSTOM = "__custom__"

async function jsonOrThrow(res: Response) {
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    if (res.status === 413) throw new Error("이미지가 너무 커요 — 4MB 이하로 줄여서 올려 주세요.")
    throw new Error(typeof data?.detail === "string" ? data.detail : `요청 실패(${res.status})`)
  }
  return data
}

/** 백엔드 role_category 와 같은 접두사 규칙(화면 그룹·라벨용). */
function categoryOf(role: string): string {
  if (/^\d{2}_face$|^face(_|$)/.test(role)) return "face"
  if (/^\d{2}_body$|^body(_|$)/.test(role)) return "body"
  if (role.startsWith("hair_")) return "hair"
  if (role.startsWith("pose_")) return "pose"
  return "other"
}

/** 파일 이름으로 역할 추정 — "hair_03_bun.png" → "hair_03_bun". 얼굴·체형·헤어·포즈 이름이 아니면 ""
 * ("IMG_1234.jpg" 같은 이름이 역할로 잘못 들어가지 않게 — 그런 건 대표가 직접 고른다). */
function guessRole(name: string, re: RegExp): string {
  const base = name.replace(/\.[^.]+$/, "").trim().toLowerCase().replace(/[\s-]+/g, "_")
  return re.test(base) && categoryOf(base) !== "other" ? base : ""
}

function StudioInner() {
  const params = useSearchParams()
  const router = useRouter()
  const characterId = params.get("character") || DEFAULT_CHARACTER
  const [characters, setCharacters] = useState<Character[]>([])
  const [presets, setPresets] = useState<Presets | null>(null)
  const [view, setView] = useState<View | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busyRef, setBusyRef] = useState<number | null>(null)

  const roleRe = useMemo(() => new RegExp(presets?.pattern || ROLE_FALLBACK), [presets])
  const catLabel = useMemo(() => {
    const m: Record<string, string> = { other: "기타" }
    presets?.categories.forEach((c) => (m[c.key] = c.label))
    return m
  }, [presets])

  const load = useCallback(
    () =>
      fetch(`/api/studio/characters/${encodeURIComponent(characterId)}`, { cache: "no-store" })
        .then(jsonOrThrow)
        .then((data: View) => {
          setView(data)
          setError(null)
        })
        .catch((e) => setError(e instanceof Error ? e.message : "불러오기 실패"))
        .finally(() => setLoading(false)),
    [characterId],
  )

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    fetch("/api/studio/roles").then(jsonOrThrow).then(setPresets).catch(() => setPresets(null))
    fetch("/api/studio/characters").then(jsonOrThrow).then((d) => setCharacters(d.characters ?? [])).catch(() => {})
  }, [])

  async function act(ref: Ref, action: "confirm" | "discard") {
    if (action === "discard" && ref.status === "confirmed" && !window.confirm(`${ref.role} 확정 이미지를 버릴까요? 이 역할은 미확정이 됩니다.`)) return
    setBusyRef(ref.id)
    try {
      await jsonOrThrow(await fetch(`/api/studio/refs/${ref.id}/${action}`, { method: "POST" }))
      toast.success(action === "confirm" ? `${ref.role} 확정을 바꿨어요` : "버렸어요")
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "실패")
    } finally {
      setBusyRef(null)
    }
  }

  // 필수 역할은 이미지가 없어도 칸을 보여 준다.
  const slots = useMemo(() => {
    const list = [...(view?.roles ?? [])]
    for (const r of view?.required ?? []) {
      if (!list.some((s) => s.role === r)) list.push({ role: r, category: categoryOf(r), confirmed: null, candidates: [] })
    }
    return list.sort((a, b) => a.role.localeCompare(b.role))
  }, [view])

  const missing = view?.missing_required ?? []
  const readyText = view?.ready ? "준비 완료" : `${missing.map((r) => REQUIRED_KO[r] ?? r).join("·")} 필요`

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-auto p-4">
      <div className="flex flex-col gap-2 pl-10 md:flex-row md:items-center md:justify-between md:pl-0">
        <div className="flex flex-wrap items-center gap-2">
          <UserRound className="h-5 w-5 text-primary" />
          <h1 className="text-lg font-semibold text-foreground">캐릭터 스튜디오</h1>
          {characters.length > 1 ? (
            <select
              value={characterId}
              onChange={(e) => router.replace(`/studio?character=${encodeURIComponent(e.target.value)}`)}
              className="rounded-md border border-border bg-background px-2 py-1 text-sm text-foreground"
            >
              {characters.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          ) : (
            view && <span className="text-sm text-muted-foreground">{view.character.name}</span>
          )}
          {view && (
            <span
              className={`flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                view.ready ? "bg-emerald-500/15 text-emerald-400" : "bg-amber-500/10 text-amber-400"
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${view.ready ? "bg-emerald-500" : "bg-amber-400"}`} />
              {readyText}
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground">얼굴(01_face)·체형(02_body)이 확정되면 착장 생성에 쓸 수 있어요.</p>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> 불러오는 중…
        </div>
      ) : error ? (
        <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-400">{error}</div>
      ) : (
        view && (
          <>
            <ImportPanel
              characterId={view.character.id}
              roleRe={roleRe}
              presets={presets}
              existing={slots.map((s) => s.role)}
              catLabel={catLabel}
              onDone={load}
            />
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {slots.map((s) => (
                <RoleCard
                  key={s.role}
                  characterId={view.character.id}
                  slot={s}
                  label={catLabel[s.category] ?? s.category}
                  required={view.required.includes(s.role)}
                  busyRef={busyRef}
                  onAct={act}
                  onChanged={load}
                />
              ))}
            </div>
          </>
        )
      )}
    </div>
  )
}

async function uploadOne(characterId: string, file: File, role: string, confirm: boolean) {
  const prepared = await prepareFile(file, categoryOf(role) === "body" ? 3072 : 2048)
  const fd = new FormData()
  fd.append("file", prepared, prepared.name)
  fd.append("role", role)
  fd.append("confirm", confirm ? "true" : "false")
  return jsonOrThrow(await fetch(`/api/studio/characters/${encodeURIComponent(characterId)}/upload`, { method: "POST", body: fd }))
}

function ImportPanel({ characterId, roleRe, presets, existing, catLabel, onDone }: {
  characterId: string
  roleRe: RegExp
  presets: Presets | null
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

  // 드롭다운 = 필수 역할 + 예시 + 이미 있는 역할 + 파일 이름에서 추정한 역할(분류별 묶음).
  const options = useMemo(() => {
    const all = new Set<string>([...(presets?.required ?? ["01_face", "02_body"]), ...(presets?.examples ?? []), ...existing])
    items.forEach((it) => it.role && roleRe.test(it.role) && all.add(it.role))
    const groups: Record<string, string[]> = {}
    ;[...all].sort().forEach((r) => (groups[categoryOf(r)] ??= []).push(r))
    return groups
  }, [presets, existing, items, roleRe])

  function add(files: FileList | File[]) {
    const list = Array.from(files)
    const ok = list.filter((f) => /\.(png|jpe?g|webp)$/i.test(f.name))
    if (ok.length < list.length) toast.error(`png·jpg·webp 이 아닌 ${list.length - ok.length}개는 뺐어요`)
    setItems((prev) => [
      ...prev,
      ...ok.map((file, i) => ({
        key: `${Date.now()}-${i}-${file.name}`,
        file,
        preview: URL.createObjectURL(file),
        role: guessRole(file.name, roleRe),
        custom: false,
        state: "idle" as const,
      })),
    ])
  }

  function update(key: string, patch: Partial<Staged>) {
    setItems((prev) => prev.map((it) => (it.key === key ? { ...it, ...patch } : it)))
  }

  function remove(key: string) {
    setItems((prev) => {
      const it = prev.find((x) => x.key === key)
      if (it) URL.revokeObjectURL(it.preview)
      return prev.filter((x) => x.key !== key)
    })
  }

  const pending = items.filter((it) => it.state === "idle" || it.state === "error")
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
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-foreground">기존 이미지 가져오기</h2>
          <p className="text-[11px] text-muted-foreground">
            여러 장을 한 번에 끌어다 놓고 이미지마다 역할을 지정하세요. 파일 이름이 역할 이름이면(예: hair_01_straight.png) 자동으로 채워져요.
          </p>
        </div>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} disabled={running} />
          바로 확정(끄면 후보로 등록)
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
        className={`flex min-h-[96px] cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border border-dashed px-3 py-4 text-center text-xs transition-colors ${
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
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((it) => {
              const bad = (it.state === "idle" || it.state === "error") && !roleRe.test(it.role)
              const inOptions = Object.values(options).some((g) => g.includes(it.role))
              const selectValue = it.custom || (it.role && !inOptions) ? CUSTOM : it.role
              return (
                <div key={it.key} className="flex gap-2 rounded-lg border border-border bg-background p-2">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={it.preview} alt={it.file.name} className="h-20 w-16 shrink-0 rounded-md bg-secondary/30 object-cover" />
                  <div className="flex min-w-0 flex-1 flex-col gap-1">
                    <div className="flex items-center gap-1">
                      <p className="truncate text-[11px] text-muted-foreground" title={it.file.name}>{it.file.name}</p>
                      {it.state !== "uploading" && (
                        <button onClick={() => remove(it.key)} disabled={running} aria-label="빼기" className="ml-auto shrink-0 text-muted-foreground hover:text-foreground disabled:opacity-50">
                          <X className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                    <select
                      value={selectValue}
                      disabled={running || it.state === "done"}
                      onChange={(e) =>
                        e.target.value === CUSTOM
                          ? update(it.key, { custom: true })
                          : update(it.key, { role: e.target.value, custom: false })
                      }
                      className={`rounded-md border bg-background px-1.5 py-1 text-xs text-foreground ${bad ? "border-amber-500/50" : "border-border"}`}
                    >
                      <option value="">역할 선택…</option>
                      {Object.entries(options).map(([cat, roles]) => (
                        <optgroup key={cat} label={catLabel[cat] ?? cat}>
                          {roles.map((r) => (
                            <option key={r} value={r}>{r}</option>
                          ))}
                        </optgroup>
                      ))}
                      <option value={CUSTOM}>직접 입력…</option>
                    </select>
                    {selectValue === CUSTOM && (
                      <input
                        value={it.role}
                        disabled={running || it.state === "done"}
                        onChange={(e) => update(it.key, { role: e.target.value.trim().toLowerCase() })}
                        placeholder="예: hair_03_ponytail"
                        className={`rounded-md border bg-background px-1.5 py-1 text-xs text-foreground ${bad ? "border-amber-500/50" : "border-border"}`}
                      />
                    )}
                    <p className="text-[11px]">
                      {it.state === "uploading" ? (
                        <span className="flex items-center gap-1 text-primary"><Loader2 className="h-3 w-3 animate-spin" /> 올리는 중</span>
                      ) : it.state === "done" ? (
                        <span className="flex items-center gap-1 text-emerald-400"><Check className="h-3 w-3" /> 등록됨</span>
                      ) : it.state === "error" ? (
                        <span className="text-red-400">{it.error}</span>
                      ) : bad ? (
                        <span className="text-amber-400">{it.role ? "소문자·숫자·_ 2~40자" : "역할을 골라 주세요"}</span>
                      ) : dupes.includes(it.role) ? (
                        <span className="text-amber-400">같은 역할이 여러 장 — 마지막 장이 확정돼요</span>
                      ) : (
                        <span className="text-muted-foreground">{catLabel[categoryOf(it.role)] ?? "기타"}</span>
                      )}
                    </p>
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
              disabled={running || pending.length === 0}
              className="flex min-h-[36px] items-center gap-1.5 rounded-lg bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
              {pending.length}장 등록
            </button>
          </div>
        </>
      )}
    </div>
  )
}

function RoleCard({ characterId, slot, label, required, busyRef, onAct, onChanged }: {
  characterId: string
  slot: RoleSlot
  label: string
  required: boolean
  busyRef: number | null
  onAct: (ref: Ref, action: "confirm" | "discard") => void
  onChanged: () => Promise<unknown>
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const c = slot.confirmed

  async function replace(file: File) {
    setUploading(true)
    try {
      await uploadOne(characterId, file, slot.role, true)
      toast.success(`${slot.role} 교체 — 이전 확정은 후보로 남아요`)
      await onChanged()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "업로드 실패")
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ""
    }
  }

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-foreground">
            {slot.role}
            {required && <span className="ml-1.5 text-[10px] font-medium text-primary">필수</span>}
          </p>
          <p className="text-[11px] text-muted-foreground">
            {label}
            {c?.w && c?.h ? ` · ${c.w}×${c.h}` : ""}
            {c ? ` · ${c.source === "upload" ? "업로드" : "생성"}` : ""}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {c ? (
            <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-400"><CheckCircle2 className="h-3.5 w-3.5" /> 확정</span>
          ) : (
            <span className="text-[11px] text-amber-400">미확정</span>
          )}
          <button
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
            className="ml-1 flex min-h-[32px] items-center gap-1 rounded-lg border border-border bg-background px-2 text-xs font-medium text-foreground hover:border-primary/40 disabled:opacity-50"
          >
            {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
            {c ? "교체" : "업로드"}
          </button>
          <input
            ref={inputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) replace(f)
            }}
          />
        </div>
      </div>

      <div className="relative flex h-56 items-center justify-center overflow-hidden rounded-lg bg-secondary/30">
        {c ? (
          <a href={c.url} target="_blank" rel="noreferrer" className="h-full w-full">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={c.url} alt={slot.role} className="h-full w-full object-contain" />
          </a>
        ) : (
          <ImageIcon className="h-6 w-6 text-muted-foreground/30" />
        )}
        {c && (
          <button
            onClick={() => onAct(c, "discard")}
            disabled={busyRef !== null}
            aria-label="확정 이미지 버리기"
            title="버리기"
            className="absolute right-1.5 top-1.5 rounded-md border border-border bg-background/80 p-1 text-muted-foreground hover:text-red-400 disabled:opacity-50"
          >
            {busyRef === c.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
          </button>
        )}
      </div>

      {slot.candidates.length > 0 && (
        <div className="flex flex-col gap-1">
          <p className="text-[11px] text-muted-foreground">후보 {slot.candidates.length}장</p>
          <div className="grid grid-cols-3 gap-1.5">
            {slot.candidates.map((r) => (
              <div key={r.id} className="flex flex-col gap-1">
                <a href={r.url} target="_blank" rel="noreferrer" className="block h-24 overflow-hidden rounded-md bg-secondary/30">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={r.url} alt={`${slot.role} 후보`} className="h-full w-full object-contain" />
                </a>
                <div className="flex gap-1">
                  <button
                    onClick={() => onAct(r, "confirm")}
                    disabled={busyRef !== null}
                    className="flex flex-1 items-center justify-center gap-0.5 rounded-md border border-border px-1 py-0.5 text-[11px] text-foreground hover:border-primary/40 disabled:opacity-50"
                  >
                    {busyRef === r.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                    확정
                  </button>
                  <button
                    onClick={() => onAct(r, "discard")}
                    disabled={busyRef !== null}
                    aria-label="후보 버리기"
                    className="rounded-md border border-border px-1 py-0.5 text-muted-foreground hover:text-red-400 disabled:opacity-50"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function StudioPage() {
  return (
    <Suspense fallback={null}>
      <StudioInner />
    </Suspense>
  )
}
