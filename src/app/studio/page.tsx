"use client"

import { Suspense, useCallback, useEffect, useMemo, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"
import { Loader2, Plus, Sparkles, UserRound, X } from "lucide-react"
import { GeneratePanel } from "@/components/studio/GeneratePanel"
import { ImportPanel } from "@/components/studio/ImportPanel"
import { RoleCard } from "@/components/studio/RoleCard"
import {
  BODY_ROLE, FACE_ROLE, ROLE_FALLBACK, categoryOf, jsonOrThrow, startGenerate, usd,
  type Character, type GenItem, type Job, type Ref, type RolePresets, type RoleSlot, type View,
} from "@/components/studio/studio-lib"

// 캐릭터 스튜디오(채널 공통) — 새 캐릭터(이름 + 자유 설명 → AI 가 bible·얼굴 후보) / AI로 만들기
// (얼굴 → 체형 → 헤어 → 포즈, 후보 클릭 = 확정) / 기존 이미지 가져오기(AI 역할 추천) / 역할 카드
// (확정·후보·다시 생성·고급 보기). 대표는 클릭과 선택만 — 프롬프트·파일명을 맞출 일이 없다.
// 백엔드: /studio/*(character_studio.py · character_studio_gen.py). 쇼츠 hero(/shorts/cast)·백곰(/cast)과 분리.

const DEFAULT_CHARACTER = "chaei"
const REQUIRED_KO: Record<string, string> = { [FACE_ROLE]: "얼굴", [BODY_ROLE]: "체형" }
const POLL_MS = 3000

function NewCharacterForm({ onCreated, onClose }: { onCreated: (c: Character, job: Job | null) => void; onClose: () => void }) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [busy, setBusy] = useState(false)

  async function submit() {
    setBusy(true)
    try {
      const d = await jsonOrThrow(await fetch("/api/studio/create", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, description }),
      }))
      toast.success(`${d.character.name} 등록 — 얼굴 후보를 만드는 중이에요`)
      onCreated(d.character, d.job ?? null)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "만들기 실패")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-xl border border-primary/30 bg-card p-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">새 캐릭터 만들기</h2>
        <button onClick={onClose} aria-label="닫기" className="text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>
      </div>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="이름 (예: 채이)" className="w-full min-w-0 rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground" />
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        rows={3}
        placeholder="자유롭게 설명해 주세요 (예: 서울 사는 24살 직장인, 긴 흑발, 172cm, 미니멀한 스타일)"
        className="w-full min-w-0 resize-y rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground"
      />
      <p className="text-[11px] text-muted-foreground">AI가 캐릭터 설정을 정리하고 얼굴 후보 4장을 만들어요(이미지 {usd(4 * 0.011)}).</p>
      <button
        onClick={submit}
        disabled={busy || !name.trim() || description.trim().length < 5}
        className="flex min-h-[36px] items-center gap-1.5 self-end rounded-lg bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
      >
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
        만들기
      </button>
    </div>
  )
}

function JobBar({ job, onClose }: { job: Job; onClose: () => void }) {
  const running = job.state === "queued" || job.state === "running"
  return (
    <div className={`flex min-w-0 flex-col gap-1 rounded-xl border p-2.5 text-xs ${running ? "border-primary/30 bg-primary/5" : job.failed ? "border-amber-500/30 bg-amber-500/10" : "border-emerald-500/40 bg-emerald-500/10"}`}>
      <div className="flex min-w-0 items-center gap-2">
        {running ? <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" /> : <Sparkles className="h-3.5 w-3.5 shrink-0 text-primary" />}
        <span className="min-w-0 flex-1 truncate text-foreground">
          {running ? "생성 중" : "생성 끝"} · {job.done + job.failed}/{job.total}장{job.failed ? ` (실패 ${job.failed})` : ""} · {job.roles.join(", ")}
        </span>
        <span className="shrink-0 text-muted-foreground">{usd(job.cost_usd)} / 예상 {usd(job.est_usd)}</span>
        {!running && (
          <button onClick={onClose} aria-label="닫기" className="shrink-0 text-muted-foreground hover:text-foreground"><X className="h-3.5 w-3.5" /></button>
        )}
      </div>
      {job.errors.map((e, i) => (
        <p key={i} className="break-words text-amber-400">{e}</p>
      ))}
    </div>
  )
}

function StudioInner() {
  const params = useSearchParams()
  const router = useRouter()
  const characterId = params.get("character") || DEFAULT_CHARACTER
  const [characters, setCharacters] = useState<Character[]>([])
  const [rolePresets, setRolePresets] = useState<RolePresets | null>(null)
  const [view, setView] = useState<View | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busyRef, setBusyRef] = useState<number | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [creating, setCreating] = useState(false)

  const roleRe = useMemo(() => new RegExp(rolePresets?.pattern || ROLE_FALLBACK), [rolePresets])
  const catLabel = useMemo(() => {
    const m: Record<string, string> = { other: "기타" }
    rolePresets?.categories.forEach((c) => (m[c.key] = c.label))
    return m
  }, [rolePresets])

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

  const loadCharacters = useCallback(
    () => fetch("/api/studio/characters").then(jsonOrThrow).then((d) => setCharacters(d.characters ?? [])).catch(() => {}),
    [],
  )

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    fetch("/api/studio/roles").then(jsonOrThrow).then(setRolePresets).catch(() => setRolePresets(null))
    loadCharacters()
  }, [loadCharacters])

  // 생성 작업 폴링 — 진행 중엔 3초마다 작업 상태 + 캐릭터(새 후보)를 다시 읽는다.
  const jobId = job?.id
  const jobRunning = job?.state === "queued" || job?.state === "running"
  useEffect(() => {
    if (!jobId || !jobRunning) return
    const t = setInterval(async () => {
      try {
        const j: Job = await jsonOrThrow(await fetch(`/api/studio/jobs/${encodeURIComponent(jobId)}`, { cache: "no-store" }))
        setJob(j)
        await load()
        if (j.state === "done") toast.success(j.failed ? `후보 ${j.done}장 생성 (실패 ${j.failed}장)` : `후보 ${j.done}장 생성 — 마음에 드는 것을 눌러 확정하세요`)
        else if (j.state === "failed") toast.error("생성 실패 — 사유를 확인해 주세요")
      } catch {
        /* 일시 오류 — 다음 폴링에서 재시도 */
      }
    }, POLL_MS)
    return () => clearInterval(t)
  }, [jobId, jobRunning, load])

  async function generate(items: GenItem[]): Promise<boolean> {
    if (!view) return false
    try {
      const j = await startGenerate(view.character.id, items)
      setJob(j)
      toast.message(`후보 ${j.total}장 생성 시작 · 예상 ${usd(j.est_usd)}`)
      return true
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "생성 시작 실패")
      return false
    }
  }

  async function act(ref: Ref, action: "confirm" | "discard") {
    if (action === "discard" && ref.status === "confirmed" && !window.confirm(`${ref.role} 확정 이미지를 버릴까요? 이 역할은 미확정이 됩니다.`)) return
    setBusyRef(ref.id)
    try {
      await jsonOrThrow(await fetch(`/api/studio/refs/${ref.id}/${action}`, { method: "POST" }))
      toast.success(action === "confirm" ? `${ref.role} 확정` : "버렸어요")
      await load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "실패")
    } finally {
      setBusyRef(null)
    }
  }

  // 필수 역할은 이미지가 없어도 칸을 보여 준다.
  const slots = useMemo(() => {
    const list: RoleSlot[] = [...(view?.roles ?? [])]
    for (const r of view?.required ?? []) {
      if (!list.some((s) => s.role === r)) list.push({ role: r, category: categoryOf(r), confirmed: null, candidates: [] })
    }
    return list.sort((a, b) => a.role.localeCompare(b.role))
  }, [view])

  const hasFace = slots.some((s) => s.role === FACE_ROLE && s.confirmed)
  const hasBody = slots.some((s) => s.role === BODY_ROLE && s.confirmed)
  function genGate(role: string): { ok: boolean; reason?: string } {
    if (role === FACE_ROLE) return { ok: true }
    const cat = categoryOf(role)
    if (!hasFace) return { ok: false, reason: "얼굴(01_face)을 먼저 확정해 주세요." }
    if (cat === "pose" && !hasBody) return { ok: false, reason: "체형(02_body)을 먼저 확정해 주세요." }
    return { ok: true }
  }

  const missing = view?.missing_required ?? []
  const readyText = view?.ready ? "준비 완료" : `${missing.map((r) => REQUIRED_KO[r] ?? r).join("·")} 필요`
  const generating = !!jobRunning

  return (
    <div className="flex h-full min-h-0 w-full min-w-0 flex-col gap-3 overflow-auto p-4">
      <div className="flex min-w-0 flex-col gap-1 pl-10 md:pl-0">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <UserRound className="h-5 w-5 shrink-0 text-primary" />
          <h1 className="text-lg font-semibold text-foreground">캐릭터 스튜디오</h1>
          {characters.length > 1 ? (
            <select
              value={characterId}
              onChange={(e) => router.replace(`/studio?character=${encodeURIComponent(e.target.value)}`)}
              className="min-w-0 rounded-md border border-border bg-background px-2 py-1 text-sm text-foreground"
            >
              {characters.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          ) : (
            view && <span className="text-sm text-muted-foreground">{view.character.name}</span>
          )}
          {view && (
            <span className={`flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${view.ready ? "bg-emerald-500/15 text-emerald-400" : "bg-amber-500/10 text-amber-400"}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${view.ready ? "bg-emerald-500" : "bg-amber-400"}`} />
              {readyText}
            </span>
          )}
          <button
            onClick={() => setCreating((v) => !v)}
            className="ml-auto flex min-h-[32px] shrink-0 items-center gap-1 rounded-lg border border-border bg-background px-2.5 text-xs font-medium text-foreground hover:border-primary/40"
          >
            <Plus className="h-3.5 w-3.5" /> 새 캐릭터
          </button>
        </div>
        <p className="text-xs text-muted-foreground">얼굴(01_face)·체형(02_body)이 확정되면 착장 생성에 쓸 수 있어요.</p>
      </div>

      {creating && (
        <NewCharacterForm
          onClose={() => setCreating(false)}
          onCreated={(c, j) => {
            setCreating(false)
            setJob(j)
            loadCharacters()
            router.replace(`/studio?character=${encodeURIComponent(c.id)}`)
          }}
        />
      )}

      {job && <JobBar job={job} onClose={() => setJob(null)} />}

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> 불러오는 중…
        </div>
      ) : error ? (
        <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-400">{error}</div>
      ) : (
        view && (
          <>
            <GeneratePanel
              characterId={view.character.id}
              slots={slots}
              presets={view.presets}
              generating={generating}
              onGenerate={generate}
              onSaved={load}
            />
            <ImportPanel
              characterId={view.character.id}
              roleRe={roleRe}
              presets={view.presets}
              existing={slots.map((s) => s.role)}
              catLabel={catLabel}
              onDone={load}
            />
            <div className="grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {slots.map((s) => {
                const gate = genGate(s.role)
                return (
                  <RoleCard
                    key={s.role}
                    characterId={view.character.id}
                    slot={s}
                    label={catLabel[s.category] ?? s.category}
                    required={view.required.includes(s.role)}
                    busyRef={busyRef}
                    canGenerate={gate.ok}
                    genBlockedReason={gate.reason}
                    generating={generating}
                    onAct={act}
                    onChanged={load}
                    onGenerate={generate}
                  />
                )
              })}
            </div>
          </>
        )
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
