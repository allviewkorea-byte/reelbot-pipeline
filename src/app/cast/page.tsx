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
  ExternalLink,
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
  regenerating,
  disabled,
  onZoom,
  onRegen,
}: {
  url: string | undefined
  label: string
  pending: boolean
  regenerating: boolean
  disabled: boolean
  onZoom: (src: string) => void
  onRegen: () => void
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-1">
      <div className="group relative min-h-0 flex-1 overflow-hidden rounded-lg border border-border bg-secondary/20">
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
        {/* 이 패널만 재생성하는 작은 버튼(우상단). 생성/재생성 중엔 비활성. */}
        <button
          onClick={onRegen}
          disabled={disabled || regenerating}
          title="이 컷만 다시 생성"
          className="absolute right-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-black/60 text-white opacity-0 transition-opacity hover:bg-black/80 disabled:opacity-40 group-hover:opacity-100"
        >
          <RefreshCw className={`h-3 w-3 ${regenerating ? "animate-spin" : ""}`} />
        </button>
        {/* 재생성 중: 기존 이미지 위에 스피너 오버레이(다른 패널 영향 0). */}
        {regenerating && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/40">
            <Loader2 className="h-5 w-5 animate-spin text-white" />
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
  // 개별 아스펙트 재생성 — "role:aspect" 1건만 진행(다른 패널 영향 0).
  const [regenKey, setRegenKey] = useState<string | null>(null)
  // 테스트 영상.
  const [producing, setProducing] = useState(false)
  const [testJob, setTestJob] = useState<{ progress: number; step: string } | null>(null)
  // 최신 테스트 영상(영속) — 진입 시 로드, 완료 시 갱신. 이탈/복귀해도 유지.
  const [testVideo, setTestVideo] = useState<{ video_url: string | null; youtube_url: string | null } | null>(null)
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

  // 최신 테스트 영상 로드(영속) — 이탈했다 와도 패널에 재생/링크가 남는다.
  useEffect(() => {
    let alive = true
    fetch(`/api/cast/test-video?channelId=${BAEKGOM_CHANNEL_ID}`, { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => {
        if (!alive) return
        const v = d?.video
        if (v && (v.video_url || v.youtube_url)) {
          setTestVideo({ video_url: v.video_url ?? null, youtube_url: v.youtube_url ?? null })
        }
      })
      .catch(() => {})
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

  // 개별 아스펙트 1장만 재생성 — 성공 시 그 패널 img 만 새 URL 로 교체(다른 패널 불변).
  async function handleRegenAspect(role: string, aspect: string) {
    if (generatingRole || regenKey) return
    setRegenKey(`${role}:${aspect}`)
    try {
      const res = await fetch("/api/cast/aspect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, aspect, channelId: BAEKGOM_CHANNEL_ID }),
      })
      const data = await res.json()
      if (!res.ok || !data.success) throw new Error(data.error ?? "재생성 실패")
      // 그 아스펙트 URL 만 교체(front 면 sheet_url 도 동기화). 다른 패널은 ?v= 그대로.
      setCast((prev) =>
        prev.map((c) =>
          c.role === role
            ? {
                ...c,
                aspects: { ...c.aspects, [aspect]: data.url },
                sheet_url: aspect === "front" ? data.url : c.sheet_url,
              }
            : c,
        ),
      )
      if (data.warning) toast.warning(data.warning)
      else toast.success("이 컷을 다시 생성했어요")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "재생성 중 오류가 발생했어요")
    } finally {
      setRegenKey(null)
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
      // 테스트 영상은 채널 모드(auto/semi)와 무관하게 항상 비공개로 업로드한다.
      // 프록시는 privacy 가 지정되면 모드 주입을 건너뛰고 이 값을 그대로 쓴다.
      const params: SayeonGenerateParams = { script, privacy: "private" }
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
          setTestJob(null)
          // 결과(R2 영상 + 유튜브 비공개 링크)를 패널에 표시하고 영속 저장(이탈/복귀 유지).
          const r = (s.result ?? {}) as Record<string, unknown>
          const vurl = typeof r.video_url === "string" ? r.video_url : null
          const yurl = typeof r.youtube_url === "string" ? r.youtube_url : null
          if (vurl || yurl) {
            setTestVideo({ video_url: vurl, youtube_url: yurl })
            void fetch("/api/cast/test-video", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ channelId: BAEKGOM_CHANNEL_ID, video_url: vurl, youtube_url: yurl, job_id }),
            })
          }
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
    <div className="flex h-full min-h-0 flex-col gap-2 overflow-auto p-3 md:overflow-hidden">
      {/* Header (compact). 모바일: 햄버거 자리 확보(pl-10). 데스크탑 무변경. */}
      <div className="flex shrink-0 items-center justify-between gap-3 pl-10 md:pl-0">
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
          {/* 메인 3존 — 명단(C) / 중앙(A+B) / 테스트 영상.
              모바일: 1열 스택 + 각 존 고정 높이(auto-rows) + shrink-0(그리드가 줄지 않게 →
              내용이 흘러넘쳐 하단 키비교 줄과 겹치던 문제 해소, 페이지가 스크롤). 데스크탑: 기존 3열. */}
          <div className="grid min-h-0 shrink-0 grid-cols-1 auto-rows-[460px] gap-2 md:flex-1 md:auto-rows-auto md:grid-cols-[220px_minmax(0,1fr)_280px] md:overflow-hidden">
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
                  {/* 모바일: 제목 줄 / 컨트롤 줄 세로 스택(제목 세로 깨짐·버튼 겹침 방지). 데스크탑: 기존 가로. */}
                  <div className="flex shrink-0 flex-col items-start gap-2 md:flex-row md:items-center md:justify-between">
                    <div className="flex flex-wrap items-center gap-2 md:flex-nowrap">
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
                        regenerating={regenKey === `${selected.role}:${a}`}
                        disabled={!!generatingRole || (!!regenKey && regenKey !== `${selected.role}:${a}`)}
                        onZoom={onZoom}
                        onRegen={() => handleRegenAspect(selected.role, a)}
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
                        regenerating={regenKey === `${selected.role}:${a}`}
                        disabled={!!generatingRole || (!!regenKey && regenKey !== `${selected.role}:${a}`)}
                        onZoom={onZoom}
                        onRegen={() => handleRegenAspect(selected.role, a)}
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
                  ) : testVideo?.video_url ? (
                    <video
                      src={testVideo.video_url}
                      controls
                      playsInline
                      className="h-full w-full object-contain"
                    />
                  ) : testVideo?.youtube_url ? (
                    <a
                      href={testVideo.youtube_url}
                      target="_blank"
                      rel="noreferrer"
                      className="flex flex-col items-center gap-2 text-center text-primary hover:opacity-90"
                    >
                      <ExternalLink className="h-7 w-7" />
                      <span className="text-[11px]">유튜브에서 보기(비공개)</span>
                    </a>
                  ) : (
                    <div className="flex flex-col items-center gap-1.5 px-3 text-center">
                      <Clapperboard className="h-7 w-7 text-muted-foreground/25" />
                      <span className="text-[10px] text-muted-foreground/50">아직 테스트 영상이 없어요</span>
                    </div>
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
              {testVideo?.youtube_url ? (
                <a
                  href={testVideo.youtube_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1.5 flex shrink-0 items-center justify-center gap-1 text-center text-[10px] text-primary hover:opacity-90"
                >
                  <ExternalLink className="h-3 w-3" />
                  유튜브 비공개 링크
                </a>
              ) : (
                <p className="mt-1.5 shrink-0 text-center text-[10px] text-muted-foreground/70">
                  확정된 전체 캐스트 사용
                </p>
              )}
            </div>
          </div>

          {/* ── 하단: 전체 키 비교(relative_height) ───────────────────── */}
          {/* 모바일: 가로 스크롤 + 버튼 shrink-0 → w-auto 이미지가 눌려 인접 캐릭터로
              겹치던 내부 겹침도 방지. 데스크탑: 기존 가운데 정렬(넓어 안 넘침). */}
          <div className="flex shrink-0 items-end justify-start gap-4 overflow-x-auto rounded-xl border border-border bg-card px-4 py-2 md:justify-center md:overflow-x-visible">
            <div className="flex h-24 items-end justify-center gap-4">
              {cast.map((c) => (
                <button
                  key={c.role}
                  onClick={() => setSelectedRole(c.role)}
                  title={c.name}
                  style={{ height: `${Math.round(c.relative_height * 100)}%` }}
                  className={`flex shrink-0 items-end transition-opacity hover:opacity-80 md:shrink ${
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
