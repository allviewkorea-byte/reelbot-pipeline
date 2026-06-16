"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import {
  Sparkles,
  RefreshCw,
  Loader2,
  Check,
  CheckCircle2,
  X,
  ImageIcon,
  Clapperboard,
} from "lucide-react"
import { ImageLightbox } from "@/components/character/ImageLightbox"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"
import {
  generateSayeon,
  generateSayeonScript,
  getDefaultSayeonCharacter,
  pollJobStatus,
  type JobStatus,
  type SayeonGenerateParams,
} from "@/lib/api"

// ── 아스펙트 정의 (백엔드 ASPECT_KEYS 와 1:1) ─────────────────────────────
const VIEW_ASPECTS = ["front", "threequarter", "side"] as const
const EXPR_ASPECTS = ["expr_joy", "expr_sad", "expr_angry", "expr_surprised"] as const
const ALL_ASPECTS = [...VIEW_ASPECTS, ...EXPR_ASPECTS]
const ASPECT_LABELS: Record<string, string> = {
  front: "정면",
  threequarter: "반측면",
  side: "측면",
  expr_joy: "기쁨",
  expr_sad: "슬픔",
  expr_angry: "화남",
  expr_surprised: "놀람",
}

interface CastEntry {
  role: string
  name: string
  animal: string
  personality: string
  colors: string[]
  relative_height: number
  aspects: Record<string, string>
  sheet_url: string | null
  status: "draft" | "approved"
}

interface GenProgress {
  status: "idle" | "running" | "done" | "failed"
  generated: string[]
  failed: string[]
  total: number
}

// ── 단일 아스펙트 패널 ────────────────────────────────────────────────────
function AspectPanel({
  url,
  label,
  pending,
  onZoom,
}: {
  url: string | undefined
  label: string
  pending: boolean
  onZoom: (src: string) => void
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-1">
      <div className="relative min-h-0 flex-1 overflow-hidden rounded-lg border border-border bg-secondary/20">
        {url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={url}
            alt={label}
            onClick={() => onZoom(url)}
            className="h-full w-full cursor-zoom-in object-contain transition-opacity hover:opacity-90"
          />
        ) : pending ? (
          <div className="flex h-full w-full items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-primary/70" />
          </div>
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <ImageIcon className="h-6 w-6 text-muted-foreground/25" />
          </div>
        )}
      </div>
      <span className="shrink-0 text-center text-[10px] font-medium text-muted-foreground">{label}</span>
    </div>
  )
}

export default function CastPage() {
  const [cast, setCast] = useState<CastEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedRole, setSelectedRole] = useState<string | null>(null)
  // 현재 생성 중인 역할(동시 1건) + 진행상태.
  const [generatingRole, setGeneratingRole] = useState<string | null>(null)
  const [progress, setProgress] = useState<GenProgress | null>(null)
  // 테스트 영상.
  const [producing, setProducing] = useState(false)
  const [testJob, setTestJob] = useState<{ progress: number; step: string } | null>(null)
  const [lightbox, setLightbox] = useState<{ src: string; alt: string } | null>(null)

  const refreshCast = useCallback(async (): Promise<CastEntry[]> => {
    const res = await fetch(`/api/cast?channelId=${BAEKGOM_CHANNEL_ID}`, { cache: "no-store" })
    const data = await res.json()
    const list: CastEntry[] = Array.isArray(data?.cast) ? data.cast : []
    setCast(list)
    return list
  }, [])

  // 최초 로드 — 첫 역할 자동 선택(빈 화면 방지).
  useEffect(() => {
    let alive = true
    fetch(`/api/cast?channelId=${BAEKGOM_CHANNEL_ID}`, { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => {
        if (!alive) return
        const list: CastEntry[] = Array.isArray(d?.cast) ? d.cast : []
        setCast(list)
        if (list.length > 0) setSelectedRole((prev) => prev ?? list[0].role)
      })
      .catch(() => {})
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [])

  // 생성 중이면 3.5초마다 폴링 — 아스펙트(R2)와 진행상태를 갱신, 종료 시 중단.
  useEffect(() => {
    if (!generatingRole) return
    let alive = true
    const tick = async () => {
      try {
        const [, statusRes] = await Promise.all([
          refreshCast(),
          fetch(`/api/cast/status?role=${generatingRole}`, { cache: "no-store" }).then((r) => r.json()),
        ])
        if (!alive) return
        const p: GenProgress = {
          status: statusRes?.status ?? "running",
          generated: Array.isArray(statusRes?.generated) ? statusRes.generated : [],
          failed: Array.isArray(statusRes?.failed) ? statusRes.failed : [],
          total: typeof statusRes?.total === "number" ? statusRes.total : ALL_ASPECTS.length,
        }
        setProgress(p)
        if (p.status === "done" || p.status === "failed") {
          setGeneratingRole(null)
          if (p.status === "done") {
            toast.success(
              p.failed.length
                ? `생성 완료 (일부 실패 ${p.failed.length}장 — 다시 생성 가능)`
                : "캐릭터 아스펙트 7장 생성 완료",
            )
          } else {
            toast.error("생성 실패 — 다시 시도해 주세요")
          }
        }
      } catch {
        /* 폴링 일시 실패 → 다음 틱 재시도 */
      }
    }
    void tick()
    const timer = setInterval(tick, 3500)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [generatingRole, refreshCast])

  // 생성 시작(논블로킹) — 즉시 running 표시 후 폴링이 채운다.
  async function handleGenerate(role: string) {
    if (generatingRole) return
    setProgress({ status: "running", generated: [], failed: [], total: ALL_ASPECTS.length })
    setGeneratingRole(role)
    // 재생성 시 즉시 승인 해제(낙관적).
    setCast((prev) => prev.map((c) => (c.role === role ? { ...c, status: "draft" } : c)))
    try {
      const res = await fetch("/api/cast/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, channelId: BAEKGOM_CHANNEL_ID }),
      })
      const data = await res.json()
      if (!res.ok || !data.success) throw new Error(data.error ?? "생성 시작 실패")
      toast.success("생성을 시작했어요 — 진행 상황이 실시간으로 표시됩니다")
    } catch (err) {
      setGeneratingRole(null)
      setProgress(null)
      toast.error(err instanceof Error ? err.message : "생성 시작 실패")
    }
  }

  // 확정 ↔ 확정 해제 토글. next 로 목표 상태를 보낸다(즉시 로컬 반영).
  async function handleApproveToggle(role: string, next: "approved" | "draft") {
    try {
      const res = await fetch("/api/cast/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, status: next }),
      })
      const data = await res.json()
      if (!res.ok || !data.success) throw new Error(data.error ?? "처리 실패")
      setCast((prev) => prev.map((c) => (c.role === role ? { ...c, status: next } : c)))
      toast.success(next === "approved" ? "캐릭터를 확정했어요" : "확정을 해제했어요")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "처리 중 오류가 발생했어요")
    }
  }

  // 테스트 영상 — 트렌드 가중 pick-topic → 자동 대본 → 흰곰 제작(1편). is_active 무관.
  async function handleTestVideo() {
    if (producing) return
    setProducing(true)
    setTestJob({ progress: 0, step: "준비 중…" })
    try {
      const char = await getDefaultSayeonCharacter()
      if (!char) {
        toast.error("기본 캐릭터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        setProducing(false)
        setTestJob(null)
        return
      }
      let topic = ""
      try {
        const t = await fetch(`/api/sayeon/pick-topic?channelId=${BAEKGOM_CHANNEL_ID}`).then((r) => r.json())
        if (typeof t?.topic === "string") topic = t.topic
      } catch {
        /* pick-topic 실패 → 빈 topic 폴백 */
      }
      const { script } = await generateSayeonScript(topic ? { topic } : {})
      const params: SayeonGenerateParams = { script }
      if (char.sheet_url && char.anchor) {
        params.sheet_url = char.sheet_url
        params.anchor = char.anchor
      } else if (char.spec) {
        params.character_spec = char.spec
      }
      const { job_id } = await generateSayeon(params)
      toast.success("테스트 영상 제작을 시작했어요")
      pollJobStatus(job_id, (s: JobStatus) => {
        setTestJob({ progress: s.progress ?? 0, step: s.current_step || "제작 중…" })
        if (s.status === "completed") {
          setProducing(false)
          setTestJob({ progress: 100, step: "완료" })
          toast.success("테스트 영상 제작 완료")
        } else if (s.status === "failed") {
          setProducing(false)
          setTestJob(null)
          toast.error(`제작 실패: ${s.error || "알 수 없는 오류"}`)
        }
      })
    } catch (e) {
      setProducing(false)
      setTestJob(null)
      toast.error(e instanceof Error ? e.message : "제작 시작 실패")
    }
  }

  const selected = cast.find((c) => c.role === selectedRole) ?? null
  const approvedCount = cast.filter((c) => c.status === "approved").length
  const selGenerating = !!selected && generatingRole === selected.role
  // 생성 중인 역할에서 아직 안 들어온 아스펙트는 pending(스피너)로 표시.
  const isPending = (role: string, aspect: string) =>
    generatingRole === role && !(progress?.generated.includes(aspect)) && !(progress?.failed.includes(aspect))

  function onZoom(src: string) {
    setLightbox({ src, alt: selected?.name ?? "캐스트" })
  }

  // ── 로스터 상태 점 색 ───────────────────────────────────────────────
  function statusDot(c: CastEntry): string {
    if (c.status === "approved") return "bg-emerald-500"
    if (c.aspects.front) return "bg-primary"
    return "bg-muted-foreground/40"
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-2 overflow-hidden p-3">
      {/* Header (compact) */}
      <div className="flex shrink-0 items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h1 className="text-base font-semibold text-foreground">캐릭터 시트</h1>
          {!loading && cast.length > 0 && (
            <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
              {approvedCount}/{cast.length} 확정
            </span>
          )}
        </div>
      </div>

      {loading ? (
        <div className="flex flex-1 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground/50" />
        </div>
      ) : cast.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card/40 text-center">
          <p className="text-sm font-medium text-muted-foreground">캐스트를 불러오지 못했어요</p>
          <p className="mt-1 text-xs text-muted-foreground/60">백엔드(영상 파이프라인) 연결을 확인해 주세요</p>
        </div>
      ) : (
        <>
          {/* 메인 3존 — 명단(C) / 중앙(A+B) / 테스트 영상 */}
          <div className="grid min-h-0 flex-1 grid-cols-[220px_minmax(0,1fr)_280px] gap-2 overflow-hidden">
            {/* ── C: 역할 명단 (세로로 꽉 채움) ──────────────────────── */}
            <div className="flex min-h-0 flex-col gap-1.5 overflow-hidden rounded-xl border border-border bg-card p-2">
              {cast.map((c) => {
                const active = c.role === selectedRole
                return (
                  <button
                    key={c.role}
                    onClick={() => setSelectedRole(c.role)}
                    className={`flex min-h-0 flex-1 items-center gap-2.5 rounded-lg border px-2 py-1.5 text-left transition-colors ${
                      active
                        ? "border-primary/40 bg-primary/15"
                        : "border-transparent hover:bg-white/5"
                    }`}
                  >
                    <div className="relative h-full w-auto shrink-0 overflow-hidden rounded bg-secondary/30 aspect-[3/4]">
                      {c.aspects.front ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={c.aspects.front} alt={c.name} className="h-full w-full object-contain" />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center">
                          <ImageIcon className="h-4 w-4 text-muted-foreground/30" />
                        </div>
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">{c.name}</p>
                      <p className="truncate text-[11px] text-muted-foreground">{c.animal}</p>
                    </div>
                    {generatingRole === c.role ? (
                      <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
                    ) : (
                      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${statusDot(c)}`} />
                    )}
                  </button>
                )
              })}
            </div>

            {/* ── 중앙: A(시점 3) + B(표정 4) ──────────────────────── */}
            {selected && (
              <div className="flex min-h-0 flex-col gap-2 overflow-hidden">
                {/* A: 헤더 + colors + 3 시점 */}
                <div className="flex min-h-0 flex-[3] flex-col rounded-xl border border-border bg-card p-3">
                  <div className="flex shrink-0 items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <h2 className="text-sm font-semibold text-foreground">{selected.name}</h2>
                      <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-medium text-primary">
                        {selected.animal}
                      </span>
                      {selected.status === "approved" && (
                        <span className="flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
                          <CheckCircle2 className="h-3 w-3" />
                          확정
                        </span>
                      )}
                      {/* colors 스와치 */}
                      <div className="ml-1 flex items-center gap-1">
                        {selected.colors.map((hex) => (
                          <span
                            key={hex}
                            title={hex}
                            style={{ backgroundColor: hex }}
                            className="h-3.5 w-3.5 rounded-full border border-border"
                          />
                        ))}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <button
                        onClick={() => handleGenerate(selected.role)}
                        disabled={!!generatingRole}
                        className="flex items-center gap-1.5 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-primary/40 disabled:opacity-50"
                      >
                        {selGenerating ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : selected.aspects.front ? (
                          <RefreshCw className="h-3.5 w-3.5 text-muted-foreground" />
                        ) : (
                          <Sparkles className="h-3.5 w-3.5 text-primary" />
                        )}
                        {selGenerating
                          ? `생성 중 ${progress?.generated.length ?? 0}/${progress?.total ?? ALL_ASPECTS.length}`
                          : selected.aspects.front
                            ? "다시 생성"
                            : "생성"}
                      </button>
                      {selected.status === "approved" ? (
                        <button
                          onClick={() => handleApproveToggle(selected.role, "draft")}
                          disabled={selGenerating}
                          className="flex items-center gap-1.5 rounded-lg border border-emerald-500/40 px-3 py-1.5 text-xs font-semibold text-emerald-400 transition-colors hover:bg-emerald-500/10 disabled:opacity-40"
                        >
                          <X className="h-3.5 w-3.5" />
                          확정 해제
                        </button>
                      ) : (
                        <button
                          onClick={() => handleApproveToggle(selected.role, "approved")}
                          disabled={!selected.aspects.front || selGenerating}
                          className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition-opacity hover:opacity-90 disabled:opacity-40"
                        >
                          <Check className="h-3.5 w-3.5" />
                          확정
                        </button>
                      )}
                    </div>
                  </div>
                  <p className="mt-1 shrink-0 truncate text-[11px] text-muted-foreground">{selected.personality}</p>
                  {/* 3 시점 패널 */}
                  <div className="mt-2 flex min-h-0 flex-1 gap-2">
                    {VIEW_ASPECTS.map((a) => (
                      <AspectPanel
                        key={a}
                        url={selected.aspects[a]}
                        label={ASPECT_LABELS[a]}
                        pending={isPending(selected.role, a)}
                        onZoom={onZoom}
                      />
                    ))}
                  </div>
                </div>

                {/* B: 표정 4 패널 */}
                <div className="flex min-h-0 flex-[2] flex-col rounded-xl border border-border bg-card p-3">
                  <p className="shrink-0 text-[11px] font-medium text-muted-foreground">표정</p>
                  <div className="mt-1.5 flex min-h-0 flex-1 gap-2">
                    {EXPR_ASPECTS.map((a) => (
                      <AspectPanel
                        key={a}
                        url={selected.aspects[a]}
                        label={ASPECT_LABELS[a]}
                        pending={isPending(selected.role, a)}
                        onZoom={onZoom}
                      />
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* ── 우: 테스트 영상 ──────────────────────────────────── */}
            <div className="flex min-h-0 flex-col rounded-xl border border-border bg-card p-3">
              <p className="shrink-0 text-[11px] font-medium text-muted-foreground">테스트 영상</p>
              <div className="mt-2 flex min-h-0 flex-1 items-center justify-center">
                <div className="relative flex aspect-[9/16] h-full max-h-full items-center justify-center overflow-hidden rounded-lg border border-border bg-secondary/20">
                  {producing ? (
                    <div className="flex flex-col items-center gap-2 px-3 text-center">
                      <Loader2 className="h-6 w-6 animate-spin text-primary/70" />
                      <span className="text-[11px] text-muted-foreground">{testJob?.step ?? "제작 중…"}</span>
                      {typeof testJob?.progress === "number" && (
                        <div className="h-1 w-24 overflow-hidden rounded-full bg-secondary">
                          <div className="h-full bg-primary transition-all" style={{ width: `${testJob.progress}%` }} />
                        </div>
                      )}
                    </div>
                  ) : (
                    <Clapperboard className="h-7 w-7 text-muted-foreground/25" />
                  )}
                </div>
              </div>
              <button
                onClick={handleTestVideo}
                disabled={producing}
                className="mt-2 flex shrink-0 items-center justify-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
              >
                {producing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Clapperboard className="h-4 w-4" />}
                {producing ? "제작 중…" : "테스트 영상"}
              </button>
              <p className="mt-1.5 shrink-0 text-center text-[10px] text-muted-foreground/70">
                확정된 전체 캐스트 사용
              </p>
            </div>
          </div>

          {/* ── 하단: 전체 키 비교(relative_height) ───────────────────── */}
          <div className="flex shrink-0 items-end justify-center gap-4 rounded-xl border border-border bg-card px-4 py-2">
            <div className="flex h-24 items-end justify-center gap-4">
              {cast.map((c) => (
                <button
                  key={c.role}
                  onClick={() => setSelectedRole(c.role)}
                  title={c.name}
                  style={{ height: `${Math.round(c.relative_height * 100)}%` }}
                  className={`flex items-end transition-opacity hover:opacity-80 ${
                    c.role === selectedRole ? "" : "opacity-90"
                  }`}
                >
                  {c.aspects.front ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={c.aspects.front} alt={c.name} className="h-full w-auto object-contain" />
                  ) : (
                    <div className="h-full w-8 rounded bg-secondary/40" />
                  )}
                </button>
              ))}
            </div>
          </div>
        </>
      )}

      <ImageLightbox src={lightbox?.src ?? null} alt={lightbox?.alt} onClose={() => setLightbox(null)} />
    </div>
  )
}
