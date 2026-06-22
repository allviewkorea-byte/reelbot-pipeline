"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { BookOpen, ClipboardList, Power, Globe, Lock, Sparkles, TrendingUp } from "lucide-react"
import { cn } from "@/lib/utils"
import { MUSIC_CHANNEL_ID, MUSIC_CHANNEL_NAME, fmtCount, type MusicMetrics } from "@/lib/music"
import { MusicPipeline } from "@/components/music/MusicPipeline"
import { MusicMarquee } from "@/components/music/MusicMarquee"

interface ChannelStatus {
  isActive: boolean
  mode: "auto" | "semi"
  syntheticMedia: boolean
  dailyCap: number
}

interface TrendInsight {
  analyzed_at?: string
  mood_keywords?: string[]
  hot_situations?: string[]
  summary?: string
}

const DEFAULT_STATUS: ChannelStatus = { isActive: false, mode: "semi", syntheticMedia: false, dailyCap: 3 }

export default function MusicDashboardPage() {
  const [status, setStatus] = useState<ChannelStatus>(DEFAULT_STATUS)
  const [metrics, setMetrics] = useState<MusicMetrics | null>(null)
  const [trend, setTrend] = useState<TrendInsight | null>(null)
  const [queueCount, setQueueCount] = useState(0)
  const [saving, setSaving] = useState(false)

  const loadStatus = useCallback(() => {
    fetch(`/api/channel-status?channelId=${MUSIC_CHANNEL_ID}`)
      .then((r) => r.json())
      .then((d) => {
        if (d?.success) setStatus({ isActive: d.isActive, mode: d.mode, syntheticMedia: d.syntheticMedia, dailyCap: d.dailyCap })
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    loadStatus()
    fetch("/api/music/metrics").then((r) => r.json()).then(setMetrics).catch(() => setMetrics(null))
    fetch("/api/music/trends").then((r) => r.json()).then((d) => setTrend(d?.trend ?? null)).catch(() => {})
    fetch("/api/music/queue").then((r) => r.json()).then((d) => setQueueCount(Array.isArray(d?.queue) ? d.queue.length : 0)).catch(() => {})
  }, [loadStatus])

  const patch = useCallback(
    async (body: Partial<{ isActive: boolean; mode: string; syntheticMedia: boolean; dailyCap: number }>) => {
      setSaving(true)
      // 낙관적 업데이트
      setStatus((s) => ({ ...s, ...body } as ChannelStatus))
      try {
        const res = await fetch("/api/channel-status", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ channelId: MUSIC_CHANNEL_ID, ...body }),
        })
        const d = await res.json()
        if (!d?.success) throw new Error(d?.error || "저장 실패")
        setStatus({ isActive: d.isActive, mode: d.mode, syntheticMedia: d.syntheticMedia, dailyCap: d.dailyCap })
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "저장 실패")
        loadStatus()
      } finally {
        setSaving(false)
      }
    },
    [loadStatus],
  )

  const isPublic = status.mode === "auto"
  const metricItems = [
    { label: "구독자", value: metrics?.subscriberCount },
    { label: "총 조회수", value: metrics?.viewCount },
    { label: "평균 조회수", value: metrics?.averageViews },
    { label: "영상 수", value: metrics?.videoCount },
  ]

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-auto p-4 md:p-6">
      {/* 헤더 */}
      <header className="flex flex-col gap-3 pl-10 md:pl-0">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-foreground">{MUSIC_CHANNEL_NAME}</h1>
            <p className="text-sm text-muted-foreground">
              유튜브 · 자동화 · {status.isActive ? "가동 중" : "정지"} — 운영 관제 대시보드
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {/* 공개/비공개 */}
            <button
              type="button"
              disabled={saving}
              onClick={() => patch({ mode: isPublic ? "semi" : "auto" })}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition-colors",
                isPublic ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-400" : "border-border text-muted-foreground hover:border-primary/40",
              )}
            >
              {isPublic ? <Globe className="h-3.5 w-3.5" /> : <Lock className="h-3.5 w-3.5" />}
              {isPublic ? "공개 ON" : "공개 OFF"}
            </button>
            {/* AI 표시 */}
            <button
              type="button"
              disabled={saving}
              onClick={() => patch({ syntheticMedia: !status.syntheticMedia })}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition-colors",
                status.syntheticMedia ? "border-sky-500/40 bg-sky-500/15 text-sky-400" : "border-border text-muted-foreground hover:border-primary/40",
              )}
            >
              <Sparkles className="h-3.5 w-3.5" /> AI 표시 {status.syntheticMedia ? "ON" : "OFF"}
            </button>
            {/* 하루 1/2/3 */}
            <div className="inline-flex items-center gap-1 rounded-lg border border-border bg-background px-1.5 py-1">
              <span className="px-1 text-[11px] text-muted-foreground">하루</span>
              {[1, 2, 3].map((n) => (
                <button
                  key={n}
                  type="button"
                  disabled={saving}
                  onClick={() => patch({ dailyCap: n })}
                  className={cn(
                    "rounded px-2 py-0.5 text-xs font-medium transition-colors",
                    status.dailyCap === n ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {n}
                </button>
              ))}
            </div>
            {/* 검토 대기 N */}
            <Link
              href="/music/queue"
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-xs font-medium text-muted-foreground hover:border-primary/40 hover:text-foreground"
            >
              <ClipboardList className="h-3.5 w-3.5" /> 검토 대기
              {queueCount > 0 && (
                <span className="rounded-full bg-primary/15 px-1.5 text-[10px] font-semibold text-primary">{queueCount}</span>
              )}
            </Link>
            {/* 가동/중단 */}
            <button
              type="button"
              disabled={saving}
              onClick={() => patch({ isActive: !status.isActive })}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition-opacity hover:opacity-90",
                status.isActive ? "bg-emerald-600 text-white" : "border border-border text-muted-foreground",
              )}
            >
              <Power className="h-3.5 w-3.5" /> {status.isActive ? "가동 중" : "중단"}
            </button>
          </div>
        </div>
      </header>

      {/* 메트릭 4종 */}
      <section className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
        {metricItems.map((m) => (
          <div key={m.label} className="rounded-xl border border-border bg-card p-3">
            <div className="text-[11px] font-medium text-muted-foreground">{m.label}</div>
            <div className="mt-1 text-lg font-semibold text-foreground">{fmtCount(m.value)}</div>
          </div>
        ))}
      </section>

      {/* 트렌드 + 오늘의 콘텐츠 */}
      <section className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
              <TrendingUp className="h-4 w-4 text-primary" /> 트렌드 분석
            </h2>
            <Link href="/music/guide" className="text-xs text-muted-foreground hover:text-foreground">전체 보기</Link>
          </div>
          {trend ? (
            <>
              {trend.summary && <p className="text-sm leading-relaxed text-foreground/90">💡 {trend.summary}</p>}
              {(trend.mood_keywords?.length ?? 0) > 0 && (
                <div className="flex flex-col gap-1.5">
                  <span className="text-[11px] font-medium text-muted-foreground">뜨는 무드</span>
                  <div className="flex flex-wrap gap-1.5">
                    {trend.mood_keywords!.slice(0, 8).map((m) => (
                      <span key={m} className="rounded-full bg-primary/15 px-2 py-0.5 text-xs text-primary">{m}</span>
                    ))}
                  </div>
                </div>
              )}
              {trend.analyzed_at && (
                <span className="text-[11px] text-muted-foreground/70">분석: {new Date(trend.analyzed_at).toLocaleDateString("ko-KR")}</span>
              )}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">트렌드 분석 데이터가 아직 없습니다.</p>
          )}
        </div>

        <div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-semibold text-foreground">오늘의 콘텐츠</h2>
          <p className="text-sm text-muted-foreground">
            자동 제작은 매일 새벽 1회 실행됩니다. 가동 {status.isActive ? "ON" : "OFF"} · 모드 {isPublic ? "공개" : "비공개"} · 하루 {status.dailyCap}개.
          </p>
          <div className="mt-1 rounded-lg border border-border bg-secondary/20 p-3 text-sm text-foreground/90">
            다음 자동 제작 → 트렌드 가중 주제로 {status.dailyCap}개 생성 후 {isPublic ? "공개 업로드" : "검토 대기 적재"}
          </div>
        </div>
      </section>

      {/* 파이프라인 */}
      <section className="flex flex-col gap-2 rounded-xl border border-border bg-card p-4">
        <h2 className="text-sm font-semibold text-foreground">음악 파이프라인</h2>
        <MusicPipeline />
      </section>

      {/* 최근 업로드 마퀴 */}
      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-medium uppercase tracking-wider text-muted-foreground">최근 업로드</h2>
        <MusicMarquee />
      </section>

      <div className="flex justify-end">
        <Link href="/music/guide" className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
          <BookOpen className="h-3.5 w-3.5" /> 테마 가이드
        </Link>
      </div>
    </div>
  )
}
