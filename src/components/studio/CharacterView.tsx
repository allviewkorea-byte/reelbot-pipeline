"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { ArrowLeft, CheckCircle2, ImageIcon, Loader2, RefreshCw, Sparkles, X } from "lucide-react"
import { CustomPromptPanel } from "./CustomPromptPanel"
import { GeneratePanel } from "./GeneratePanel"
import { ImportPanel } from "./ImportPanel"
import { Lightbox } from "./Lightbox"
import { MeasurementsCard } from "./MeasurementsCard"
import { RoleCard } from "./RoleCard"
import {
  BODY_ROLE, FACE_ROLE, ROLE_FALLBACK, categoryOf, channelName, jsonOrThrow, roleName, startGenerate,
  type GenItem, type Job, type Ref, type RolePresets, type RoleSlot, type View,
} from "./studio-lib"

// 캐릭터 화면 — 기본은 사진과 큰 버튼만: 준비 배지 + 얼굴·체형 큰 카드 + 헤어 갤러리(한글 이름).
// 사진 클릭 = 크게 보기(확정 변경은 그 안에서만). 역할 코드·프롬프트·비용은 "전문가 모드"(기본 꺼짐) 뒤에만.

const POLL_MS = 3000
const EXPERT_KEY = "studio-expert"

function readExpert(): boolean {
  try {
    return window.localStorage.getItem(EXPERT_KEY) === "1"
  } catch {
    return false
  }
}

function refsOf(slot: RoleSlot | undefined): Ref[] {
  return slot ? [...(slot.confirmed ? [slot.confirmed] : []), ...slot.candidates] : []
}

function Photo({ refs, title, big, busy, onOpen }: { refs: Ref[]; title: string; big?: boolean; busy: boolean; onOpen: (i: number) => void }) {
  const main = refs[0]
  const confirmed = main?.status === "confirmed"
  return (
    <div className={`relative flex w-full items-center justify-center overflow-hidden rounded-xl bg-secondary/30 ${big ? "aspect-[3/4] max-h-[460px]" : "aspect-[3/4]"}`}>
      {main && confirmed ? (
        <button type="button" onClick={() => onOpen(0)} title="크게 보기" className="h-full w-full">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={main.url} alt={title} className="h-full w-full object-cover" />
        </button>
      ) : refs.length > 0 ? (
        // 아직 고르지 않은 후보들 — 눌러서 크게 보고 고른다
        <div className={`grid h-full w-full gap-1 p-1 ${refs.length > 1 ? "grid-cols-2" : ""}`}>
          {refs.slice(0, 4).map((r, i) => (
            <button key={r.id} type="button" onClick={() => onOpen(i)} title="크게 보기" className="overflow-hidden rounded-lg">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={r.url} alt={`${title} 후보`} className="h-full w-full object-cover" />
            </button>
          ))}
        </div>
      ) : (
        <ImageIcon className="h-8 w-8 text-muted-foreground/30" />
      )}
      {busy && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-background/70 text-xs text-primary">
          <Loader2 className="h-6 w-6 animate-spin" /> 만드는 중
        </div>
      )}
    </div>
  )
}

export function CharacterView({ characterId, initialJobId }: { characterId: string; initialJobId: string | null }) {
  const [view, setView] = useState<View | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [jobId, setJobId] = useState<string | null>(initialJobId)
  const [busyRef, setBusyRef] = useState<number | null>(null)
  const [box, setBox] = useState<{ role: string; index: number } | null>(null)
  const [expert, setExpert] = useState(false)
  const [rolePresets, setRolePresets] = useState<RolePresets | null>(null)

  useEffect(() => {
    // 브라우저 저장값은 마운트 후 읽는다(서버 렌더와 어긋나지 않게)
    const t = setTimeout(() => setExpert(readExpert()), 0)
    return () => clearTimeout(t)
  }, [])

  const load = useCallback(
    () =>
      fetch(`/api/studio/characters/${encodeURIComponent(characterId)}`, { cache: "no-store" })
        .then(jsonOrThrow)
        .then((d: View) => {
          setView(d)
          setError(null)
        })
        .catch((e) => setError(e instanceof Error ? e.message : "불러오지 못했어요")),
    [characterId],
  )

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!expert || rolePresets) return
    fetch("/api/studio/roles").then(jsonOrThrow).then(setRolePresets).catch(() => {})
  }, [expert, rolePresets])

  // 생성 작업 폴링 — 진행 중엔 3초마다 상태 + 새 후보
  const running = !!jobId && (!job || job.state === "queued" || job.state === "running")
  useEffect(() => {
    if (!jobId || !running) return
    const t = setInterval(async () => {
      try {
        const j: Job = await jsonOrThrow(await fetch(`/api/studio/jobs/${encodeURIComponent(jobId)}`, { cache: "no-store" }))
        setJob(j)
        await load()
        if (j.state === "done") toast.success(j.failed ? `사진 ${j.done}장을 만들었어요 (${j.failed}장 실패)` : `사진 ${j.done}장을 만들었어요. 눌러서 골라 주세요`)
        else if (j.state === "failed") toast.error("사진을 만들지 못했어요")
      } catch {
        setJobId(null) // 서버 재시작 등으로 작업이 사라짐 — 이미 만든 사진은 화면에 남는다
      }
    }, POLL_MS)
    return () => clearInterval(t)
  }, [jobId, running, load])

  function toggleExpert(on: boolean) {
    setExpert(on)
    try {
      window.localStorage.setItem(EXPERT_KEY, on ? "1" : "0")
    } catch {
      /* 저장 못 해도 이번 화면에선 동작 */
    }
  }

  async function generate(items: GenItem[]): Promise<boolean> {
    try {
      const j = await startGenerate(characterId, items)
      setJob(j)
      setJobId(j.id)
      return true
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "시작하지 못했어요")
      return false
    }
  }

  async function act(ref: Ref, action: "confirm" | "discard") {
    if (action === "discard" && !window.confirm(ref.status === "confirmed" ? "지금 쓰는 사진이에요. 지울까요?" : "이 사진을 지울까요?")) return
    setBusyRef(ref.id)
    try {
      await jsonOrThrow(await fetch(`/api/studio/refs/${ref.id}/${action}`, { method: "POST" }))
      toast.success(action === "confirm" ? "사진을 바꿨어요" : "지웠어요")
      await load()
      if (action === "discard") setBox(null)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "실패했어요")
    } finally {
      setBusyRef(null)
    }
  }

  const slots = useMemo(() => {
    const list: RoleSlot[] = [...(view?.roles ?? [])]
    for (const r of view?.required ?? []) {
      if (!list.some((s) => s.role === r)) list.push({ role: r, category: categoryOf(r), confirmed: null, candidates: [] })
    }
    return list.sort((a, b) => a.role.localeCompare(b.role))
  }, [view])
  const bySlot = useMemo(() => Object.fromEntries(slots.map((s) => [s.role, s])), [slots])
  const roleRe = useMemo(() => new RegExp(rolePresets?.pattern || ROLE_FALLBACK), [rolePresets])

  if (error) return <div className="m-4 rounded-xl border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-400">{error}</div>
  if (!view) return <div className="flex items-center gap-2 p-4 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> 불러오는 중…</div>

  const presets = view.presets
  const hasFace = !!bySlot[FACE_ROLE]?.confirmed
  const hasBody = !!bySlot[BODY_ROLE]?.confirmed
  const jobRoles = new Set(running && job ? job.roles : [])
  const emptyHair = presets.hair.filter((h) => !bySlot[h.role]?.confirmed && !(bySlot[h.role]?.candidates.length))
  const boxRefs = box ? refsOf(bySlot[box.role]) : []
  const catLabel: Record<string, string> = { other: "기타" }
  rolePresets?.categories.forEach((c) => (catLabel[c.key] = c.label))

  function gate(role: string): { ok: boolean; reason?: string } {
    if (role === FACE_ROLE) return { ok: true }
    if (!hasFace) return { ok: false, reason: "얼굴을 먼저 골라 주세요" }
    if (categoryOf(role) === "pose" && !hasBody) return { ok: false, reason: "체형을 먼저 골라 주세요" }
    return { ok: true }
  }

  const big = (role: string, title: string, count: number) => {
    const slot = bySlot[role]
    const refs = refsOf(slot)
    const g = gate(role)
    const has = refs.length > 0
    return (
      <div className="flex min-w-0 flex-col gap-3 rounded-xl border border-border bg-card p-4">
        <div className="flex items-center justify-between gap-2">
          <p className="text-base font-semibold text-foreground">{title}</p>
          {slot?.confirmed ? (
            <CheckCircle2 className="h-5 w-5 text-emerald-400" aria-label="골랐어요" />
          ) : has ? (
            <span className="text-xs text-amber-400">하나를 골라 주세요</span>
          ) : null}
        </div>
        <Photo refs={refs} title={title} big busy={jobRoles.has(role)} onOpen={(i) => setBox({ role, index: i })} />
        {slot?.confirmed && slot.candidates.length > 0 && (
          <button onClick={() => setBox({ role, index: 1 })} className="self-start text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline">
            다른 사진 {slot.candidates.length}장 보기
          </button>
        )}
        <button onClick={() => generate([{ role, count }])} disabled={!g.ok || running}
          className="flex min-h-[44px] items-center justify-center gap-1.5 rounded-lg border border-border bg-background px-4 text-sm font-medium text-foreground hover:border-primary/40 disabled:opacity-50">
          {has ? <RefreshCw className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />} {has ? "다시 만들기" : "만들기"}
        </button>
        {!g.ok && <p className="text-xs text-muted-foreground">{g.reason}</p>}
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 w-full min-w-0 flex-col gap-5 overflow-auto p-4 md:p-6">
      <div className="flex min-w-0 flex-col gap-3 pl-10 md:pl-0">
        <Link href="/studio" className="flex items-center gap-1 self-start text-xs text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" /> 캐릭터 목록
        </Link>
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold text-foreground">{view.character.name}</h1>
          <span className="text-xs text-muted-foreground">{channelName(view.character.channel_id)}</span>
          <span className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium ${view.ready ? "bg-emerald-500/15 text-emerald-400" : "bg-amber-500/10 text-amber-400"}`}>
            <span className={`h-2 w-2 rounded-full ${view.ready ? "bg-emerald-500" : "bg-amber-400"}`} />
            {view.ready ? "준비 완료" : hasFace ? "체형 사진이 필요해요" : "얼굴 사진이 필요해요"}
          </span>
          <label className="ml-auto flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
            전문가 모드
            <button type="button" role="switch" aria-checked={expert} onClick={() => toggleExpert(!expert)}
              className={`relative h-5 w-9 rounded-full transition-colors ${expert ? "bg-primary" : "bg-secondary"}`}>
              <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-background transition-all ${expert ? "left-[18px]" : "left-0.5"}`} />
            </button>
          </label>
        </div>
      </div>

      {job && (
        <div className={`flex min-w-0 items-center gap-2 rounded-xl border p-3 text-sm ${running ? "border-primary/30 bg-primary/5 text-foreground" : job.failed ? "border-amber-500/30 bg-amber-500/10 text-amber-400" : "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"}`}>
          {running ? <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" /> : <CheckCircle2 className="h-4 w-4 shrink-0" />}
          <span className="min-w-0 flex-1">
            {running ? `사진 만드는 중… ${job.done + job.failed}/${job.total}장` : job.failed ? `${job.done}장 완성, ${job.failed}장은 만들지 못했어요` : `${job.done}장 완성 — 눌러서 골라 주세요`}
            {!running && job.errors.length > 0 && expert && <span className="mt-1 block break-words text-xs">{job.errors.join(" · ")}</span>}
          </span>
          {!running && <button onClick={() => { setJob(null); setJobId(null) }} aria-label="닫기" className="shrink-0 opacity-70 hover:opacity-100"><X className="h-4 w-4" /></button>}
        </div>
      )}

      <div className="grid min-w-0 gap-4 md:grid-cols-2">
        {big(FACE_ROLE, "얼굴", 4)}
        {big(BODY_ROLE, "체형", 2)}
      </div>

      <MeasurementsCard characterId={characterId} />

      <section className="flex min-w-0 flex-col gap-4 rounded-xl border border-border bg-card p-4">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h2 className="text-base font-semibold text-foreground">헤어</h2>
          {emptyHair.length > 0 && (
            <button onClick={() => generate(emptyHair.map((h) => ({ role: h.role, count: 2 })))} disabled={!hasFace || running}
              className="ml-auto flex min-h-[40px] items-center gap-1.5 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              <Sparkles className="h-4 w-4" /> 빈 헤어 {emptyHair.length}개 한꺼번에 만들기
            </button>
          )}
        </div>
        {!hasFace && <p className="text-xs text-muted-foreground">얼굴을 먼저 골라 주세요.</p>}
        <div className="grid min-w-0 grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
          {presets.hair.map((h) => {
            const slot = bySlot[h.role]
            const refs = refsOf(slot)
            const pick = !slot?.confirmed && refs.length > 0
            return (
              <div key={h.role} className="flex min-w-0 flex-col gap-2">
                <Photo refs={refs} title={roleName(h.role, presets)} busy={jobRoles.has(h.role)} onOpen={(i) => setBox({ role: h.role, index: i })} />
                <div className="flex min-w-0 items-center justify-between gap-1">
                  <span className="truncate text-sm font-medium text-foreground">{roleName(h.role, presets)}</span>
                  {slot?.confirmed ? <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" /> : pick ? <span className="shrink-0 text-[11px] text-amber-400">골라 주세요</span> : null}
                </div>
                <button onClick={() => generate([{ role: h.role, count: 2 }])} disabled={!hasFace || running}
                  className="flex min-h-[36px] items-center justify-center gap-1 rounded-lg border border-border bg-background px-2 text-xs font-medium text-foreground hover:border-primary/40 disabled:opacity-50">
                  {refs.length ? <RefreshCw className="h-3.5 w-3.5" /> : <Sparkles className="h-3.5 w-3.5" />} {refs.length ? "다시 만들기" : "만들기"}
                </button>
              </div>
            )
          })}
        </div>
      </section>

      {expert && (
        <section className="flex min-w-0 flex-col gap-4">
          <h2 className="text-sm font-semibold text-muted-foreground">전문가 모드</h2>
          <CustomPromptPanel slots={slots} presets={presets} generating={running} onGenerate={generate} />
          <GeneratePanel characterId={characterId} slots={slots} presets={presets} generating={running} onGenerate={generate} onSaved={load} />
          <ImportPanel characterId={characterId} roleRe={roleRe} presets={presets} existing={slots.map((s) => s.role)} catLabel={catLabel} onDone={load} />
          <div className="grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {slots.map((s) => {
              const g = gate(s.role)
              return (
                <RoleCard key={s.role} characterId={characterId} slot={s} label={roleName(s.role, presets)}
                  required={view.required.includes(s.role)} busyRef={busyRef} canGenerate={g.ok} genBlockedReason={g.reason}
                  generating={running} onAct={act} onOpen={(role, ref) => setBox({ role, index: Math.max(0, refsOf(bySlot[role]).findIndex((r) => r.id === ref.id)) })}
                  onChanged={load} onGenerate={generate} />
              )
            })}
          </div>
        </section>
      )}

      {box && boxRefs.length > 0 && (
        <Lightbox title={roleName(box.role, presets)} refs={boxRefs} index={Math.min(box.index, boxRefs.length - 1)} busy={busyRef !== null}
          onIndex={(i) => setBox({ role: box.role, index: i })} onClose={() => setBox(null)}
          onConfirm={(r) => act(r, "confirm").then(() => setBox({ role: box.role, index: 0 }))} onDiscard={(r) => act(r, "discard")} />
      )}
    </div>
  )
}
