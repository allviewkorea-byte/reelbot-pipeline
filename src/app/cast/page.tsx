"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import {
  Sparkles,
  RefreshCw,
  Loader2,
  Check,
  CheckCircle2,
  ImageIcon,
  ZoomIn,
  Clapperboard,
} from "lucide-react"
import { ImageLightbox } from "@/components/character/ImageLightbox"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"
import {
  generateSayeon,
  generateSayeonScript,
  getDefaultSayeonCharacter,
  pollJobStatus,
  type SayeonGenerateParams,
} from "@/lib/api"

// ── 캐스트 카드 타입(/api/cast 응답과 1:1) ─────────────────────────────
interface CastEntry {
  role: string
  name: string
  animal: string
  personality: string
  filename: string
  sheet_url: string | null
  status: "draft" | "approved"
}

export default function CastPage() {
  const [cast, setCast] = useState<CastEntry[]>([])
  const [loading, setLoading] = useState(true)
  // 역할별 생성 진행 상태(중복 클릭 방지 + 스피너).
  const [busyRole, setBusyRole] = useState<string | null>(null)
  // 테스트 영상 제작 진행 표시(가동 토글 is_active 와 무관 — 1편만 제작).
  const [producing, setProducing] = useState(false)
  // 이미지 확대 라이트박스.
  const [lightbox, setLightbox] = useState<{ src: string; alt: string } | null>(null)

  // 핸들러(생성/확정 후)에서 목록을 다시 불러온다. 로딩 표시는 건드리지 않는다.
  const fetchCast = useCallback(async () => {
    try {
      const res = await fetch(`/api/cast?channelId=${BAEKGOM_CHANNEL_ID}`, { cache: "no-store" })
      const data = await res.json()
      setCast(Array.isArray(data?.cast) ? data.cast : [])
    } catch {
      /* 새로고침 실패 → 기존 목록 유지 */
    }
  }, [])

  // 마운트 시 최초 로드 — setState 는 비동기 콜백 안에서만(effect 본문 직접 호출 회피).
  useEffect(() => {
    let alive = true
    fetch(`/api/cast?channelId=${BAEKGOM_CHANNEL_ID}`, { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => {
        if (alive) setCast(Array.isArray(d?.cast) ? d.cast : [])
      })
      .catch(() => {
        /* 실패 → 빈 목록(안내 문구) */
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [])

  // 역할별 시트 생성/재생성 → 성공 시 목록 갱신.
  async function handleGenerate(role: string) {
    if (busyRole) return
    setBusyRole(role)
    try {
      const res = await fetch("/api/cast/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, channelId: BAEKGOM_CHANNEL_ID }),
      })
      const data = await res.json()
      if (!res.ok || !data.success) throw new Error(data.error ?? "시트 생성 실패")
      toast.success("시트를 생성했어요")
      await fetchCast()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "생성 중 오류가 발생했어요")
    } finally {
      setBusyRole(null)
    }
  }

  // 승인(확정) → status=approved.
  async function handleApprove(role: string) {
    try {
      const res = await fetch("/api/cast/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role }),
      })
      const data = await res.json()
      if (!res.ok || !data.success) throw new Error(data.error ?? "확정 실패")
      setCast((prev) => prev.map((c) => (c.role === role ? { ...c, status: "approved" } : c)))
      toast.success("캐릭터를 확정했어요")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "확정 중 오류가 발생했어요")
    }
  }

  // 테스트 영상 — 대시보드 시작 버튼과 동일한 produce 경로(트렌드 가중 pick-topic →
  // 자동 대본 → 흰곰 제작). ★ 가동 토글(is_active)은 건드리지 않는다(1편만 제작).
  // 업로드 공개/비공개는 기존 모드 토글 설정을 generate 프록시가 그대로 따른다(#129).
  async function handleTestVideo() {
    if (producing) return
    setProducing(true)
    try {
      const char = await getDefaultSayeonCharacter()
      if (!char) {
        toast.error("기본 캐릭터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        setProducing(false)
        return
      }
      let topic = ""
      try {
        const t = await fetch(`/api/sayeon/pick-topic?channelId=${BAEKGOM_CHANNEL_ID}`).then((r) => r.json())
        if (typeof t?.topic === "string") topic = t.topic
      } catch {
        /* pick-topic 실패 → 빈 topic 폴백(제작은 계속) */
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
      toast.success("테스트 영상 제작을 시작했어요 — 대시보드 파이프라인에서 확인하세요.")
      pollJobStatus(job_id, (s) => {
        if (s.status === "completed") {
          setProducing(false)
          toast.success("테스트 영상 제작 완료")
        } else if (s.status === "failed") {
          setProducing(false)
          toast.error(`제작 실패: ${s.error || "알 수 없는 오류"}`)
        }
      })
    } catch (e) {
      setProducing(false)
      toast.error(e instanceof Error ? e.message : "제작 시작 실패")
    }
  }

  const approvedCount = cast.filter((c) => c.status === "approved").length

  return (
    <div className="flex flex-1 flex-col gap-6 overflow-auto p-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-foreground">캐릭터 시트</h1>
            {!loading && cast.length > 0 && (
              <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                {approvedCount}/{cast.length} 확정
              </span>
            )}
          </div>
          <p className="mt-0.5 text-sm text-muted-foreground">
            사연 동물 캐스트의 시트를 생성·재생성·확정하고, 테스트 영상을 만들어 보세요
          </p>
        </div>

        {/* 테스트 영상 — 1편만 제작(트렌드 가중). 가동 토글과 무관. */}
        <button
          onClick={handleTestVideo}
          disabled={producing}
          className="flex shrink-0 items-center gap-1.5 rounded-lg bg-primary px-3.5 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          {producing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Clapperboard className="h-4 w-4" />}
          {producing ? "제작 중…" : "테스트 영상"}
        </button>
      </div>

      {/* 캐스트 그리드 */}
      {loading ? (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="overflow-hidden rounded-xl border border-border bg-card animate-pulse">
              <div className="aspect-[2/3] bg-secondary/50" />
              <div className="space-y-2 p-3">
                <div className="h-3.5 w-2/3 rounded bg-secondary/60" />
                <div className="h-3 w-full rounded bg-secondary/40" />
              </div>
            </div>
          ))}
        </div>
      ) : cast.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card/40 py-16 text-center">
          <p className="text-sm font-medium text-muted-foreground">캐스트를 불러오지 못했어요</p>
          <p className="mt-1 text-xs text-muted-foreground/60">백엔드(영상 파이프라인) 연결을 확인해 주세요</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
          {cast.map((c) => {
            const generating = busyRole === c.role
            const approved = c.status === "approved"
            return (
              <div
                key={c.role}
                className="group relative flex flex-col overflow-hidden rounded-xl border border-border bg-card"
              >
                {/* 시트 이미지 / 빈 슬롯 */}
                <div className="relative aspect-[2/3] bg-secondary/20">
                  {c.sheet_url ? (
                    <>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={c.sheet_url}
                        alt={c.name}
                        onClick={() => c.sheet_url && setLightbox({ src: c.sheet_url, alt: c.name })}
                        className="h-full w-full cursor-zoom-in object-contain transition-opacity hover:opacity-90"
                        onError={(e) => {
                          const el = e.currentTarget
                          el.style.display = "none"
                          el.nextElementSibling?.removeAttribute("hidden")
                        }}
                      />
                      <div hidden className="flex h-full w-full items-center justify-center">
                        <ImageIcon className="h-8 w-8 text-muted-foreground/30" />
                      </div>
                      <button
                        onClick={() => c.sheet_url && setLightbox({ src: c.sheet_url, alt: c.name })}
                        className="absolute right-2 top-2 flex h-7 w-7 items-center justify-center rounded-full bg-black/60 text-white opacity-0 transition-opacity group-hover:opacity-100"
                        title="확대보기"
                      >
                        <ZoomIn className="h-3.5 w-3.5" />
                      </button>
                    </>
                  ) : (
                    <div className="flex h-full w-full flex-col items-center justify-center gap-1.5 text-center">
                      <ImageIcon className="h-8 w-8 text-muted-foreground/30" />
                      <span className="text-xs text-muted-foreground/60">시트 없음</span>
                    </div>
                  )}

                  {/* 확정 뱃지 — emerald(저장/완료 액센트) */}
                  {approved && (
                    <span className="absolute left-2 top-2 flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
                      <CheckCircle2 className="h-3 w-3" />
                      확정
                    </span>
                  )}
                </div>

                {/* 정보 */}
                <div className="flex flex-1 flex-col p-3">
                  <div className="flex items-center gap-1.5">
                    <p className="truncate text-sm font-medium text-foreground">{c.name}</p>
                    <span className="shrink-0 rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-medium text-primary">
                      {c.animal}
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{c.personality}</p>

                  {/* 액션 */}
                  <div className="mt-3 flex items-center gap-2">
                    <button
                      onClick={() => handleGenerate(c.role)}
                      disabled={generating || !!busyRole}
                      className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-primary/40 disabled:opacity-50"
                    >
                      {generating ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : c.sheet_url ? (
                        <RefreshCw className="h-3.5 w-3.5 text-muted-foreground" />
                      ) : (
                        <Sparkles className="h-3.5 w-3.5 text-primary" />
                      )}
                      {generating ? "생성 중…" : c.sheet_url ? "다시 생성" : "생성"}
                    </button>
                    <button
                      onClick={() => handleApprove(c.role)}
                      disabled={!c.sheet_url || approved || generating}
                      className="flex items-center justify-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition-opacity hover:opacity-90 disabled:opacity-40"
                    >
                      <Check className="h-3.5 w-3.5" />
                      확정
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* 이미지 확대 라이트박스 */}
      <ImageLightbox src={lightbox?.src ?? null} alt={lightbox?.alt} onClose={() => setLightbox(null)} />
    </div>
  )
}
