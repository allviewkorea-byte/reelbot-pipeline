"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { Users, Eye, BarChart3, Video, ClipboardList, Play, Square, Loader2, Settings, Palette } from "lucide-react"
import { PLATFORM_BADGE, PLATFORM_LABELS, TRACK_BADGE, TRACK_LABELS } from "@/lib/channels"
import { MUSIC_CHANNEL_ID, MUSIC_CHANNEL_NAME, fmtCount, type MusicMetrics } from "@/lib/music"
import { MusicPipeline } from "@/components/music/MusicPipeline"
import { MusicMarquee } from "@/components/music/MusicMarquee"
import { MusicTrendPanel } from "@/components/music/MusicTrendPanel"
import { MusicQueuePreview } from "@/components/music/MusicQueuePreview"
import type { MusicJob } from "@/lib/music-jobs"

interface ChannelStatus {
  isActive: boolean
  mode: "auto" | "semi"
  syntheticMedia: boolean
  dailyCap: number
  trackCount: number
}

const DEFAULT_STATUS: ChannelStatus = { isActive: false, mode: "semi", syntheticMedia: false, dailyCap: 3, trackCount: 1 }

export default function MusicDashboardPage() {
  const [status, setStatus] = useState<ChannelStatus>(DEFAULT_STATUS)
  const [stats, setStats] = useState<MusicMetrics | null>(null)
  const [queueCount, setQueueCount] = useState(0)
  const [busy, setBusy] = useState(false)
  const [activeJobs, setActiveJobs] = useState<MusicJob[]>([])

  const loadStatus = useCallback(() => {
    fetch(`/api/channel-status?channelId=${MUSIC_CHANNEL_ID}`)
      .then((r) => r.json())
      .then((d) => {
        if (d?.success) setStatus({ isActive: d.isActive, mode: d.mode, syntheticMedia: d.syntheticMedia, dailyCap: d.dailyCap, trackCount: d.trackCount })
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    loadStatus()
    fetch("/api/music/metrics").then((r) => r.json()).then(setStats).catch(() => setStats(null))
    fetch("/api/music/queue").then((r) => r.json()).then((d) => setQueueCount(Array.isArray(d?.queue) ? d.queue.length : 0)).catch(() => {})
  }, [loadStatus])

  // #36 운영 가시성 — 진행 중 작업 폴링(4초) → 파이프라인 실시간 시각화.
  useEffect(() => {
    let alive = true
    const tick = () => {
      fetch("/api/music/jobs/active")
        .then((r) => r.json())
        .then((d) => { if (alive) setActiveJobs(Array.isArray(d?.jobs) ? d.jobs : []) })
        .catch(() => {})
    }
    tick()
    const id = setInterval(tick, 4000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  const patch = useCallback(
    async (body: Partial<{ isActive: boolean; mode: string; syntheticMedia: boolean; dailyCap: number; trackCount: number }>) => {
      setBusy(true)
      setStatus((s) => ({ ...s, ...body } as ChannelStatus))
      try {
        const res = await fetch("/api/channel-status", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ channelId: MUSIC_CHANNEL_ID, ...body }),
        })
        const d = await res.json()
        if (!d?.success) throw new Error(d?.error || "저장 실패")
        setStatus({ isActive: d.isActive, mode: d.mode, syntheticMedia: d.syntheticMedia, dailyCap: d.dailyCap, trackCount: d.trackCount })
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "저장 실패")
        loadStatus()
      } finally {
        setBusy(false)
      }
    },
    [loadStatus],
  )

  const { isActive, mode, syntheticMedia, dailyCap, trackCount } = status
  const isPublic = mode === "auto"

  const cards = [
    { label: "구독자", icon: Users, value: fmtCount(stats?.subscriberCount) },
    { label: "총 조회수", icon: Eye, value: fmtCount(stats?.viewCount) },
    { label: "평균 조회수", icon: BarChart3, value: fmtCount(stats?.averageViews) },
    { label: "영상 수", icon: Video, value: fmtCount(stats?.videoCount) },
  ]

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-auto p-4 md:overflow-hidden">
      {/* 헤더 — 채널명+뱃지 / 토글들. 백곰 레이아웃 1:1 */}
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0 pl-10 md:pl-0">
          <div className="flex flex-wrap items-center gap-2 md:flex-nowrap">
            <h1 className="truncate text-lg font-semibold text-foreground">{MUSIC_CHANNEL_NAME}</h1>
            <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${PLATFORM_BADGE.youtube}`}>
              {PLATFORM_LABELS.youtube}
            </span>
            <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${TRACK_BADGE.auto}`}>
              {TRACK_LABELS.auto}
            </span>
            <span
              className={`flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors duration-200 ${
                isActive ? "bg-emerald-500/15 text-emerald-400" : "bg-secondary/50 text-muted-foreground"
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${isActive ? "bg-emerald-500 animate-pulse" : "bg-muted-foreground/50"}`} />
              {isActive ? "가동 중" : "대기 중"}
            </span>
          </div>
          <p className="mt-0.5 text-sm text-muted-foreground">운영 채널 관제 대시보드</p>
        </div>

        <div className="flex shrink-0 flex-wrap items-center justify-start gap-2 md:justify-end">
          {/* 공개/비공개 */}
          <button
            onClick={() => patch({ mode: isPublic ? "semi" : "auto" })}
            disabled={busy}
            role="switch"
            aria-checked={isPublic}
            title="공개=유튜브 공개 업로드 / 비공개=비공개 업로드"
            className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium transition-colors hover:border-primary/40 disabled:opacity-60"
          >
            <span className={isPublic ? "text-emerald-400" : "text-muted-foreground"}>{isPublic ? "공개" : "비공개"}</span>
            <span className={`relative h-4 w-7 shrink-0 rounded-full transition-colors ${isPublic ? "bg-emerald-600" : "bg-secondary"}`}>
              <span className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${isPublic ? "left-3.5" : "left-0.5"}`} />
            </span>
          </button>
          {/* AI 표시 */}
          <button
            onClick={() => patch({ syntheticMedia: !syntheticMedia })}
            disabled={busy}
            role="switch"
            aria-checked={syntheticMedia}
            title="유튜브 업로드에 'AI 합성 콘텐츠' 표시를 켜고/끕니다"
            className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium transition-colors hover:border-primary/40 disabled:opacity-60"
          >
            <span className={syntheticMedia ? "text-emerald-400" : "text-muted-foreground"}>AI 표시 {syntheticMedia ? "ON" : "OFF"}</span>
            <span className={`relative h-4 w-7 shrink-0 rounded-full transition-colors ${syntheticMedia ? "bg-emerald-600" : "bg-secondary"}`}>
              <span className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${syntheticMedia ? "left-3.5" : "left-0.5"}`} />
            </span>
          </button>
          {/* 하루 1/2/3 */}
          <div className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium" title="하루에 자동 게시할 영상 개수">
            <span className="text-muted-foreground">하루</span>
            <div className="inline-flex rounded-md border border-border bg-background p-0.5">
              {[1, 2, 3].map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => patch({ dailyCap: n })}
                  disabled={busy}
                  aria-pressed={dailyCap === n}
                  className={`rounded px-2 py-0.5 text-xs font-medium transition-colors disabled:opacity-50 ${
                    dailyCap === n ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
            <span className="text-muted-foreground">개</span>
          </div>
          {/* 곡수 입력창 1~100 (#40) — 영상 1개당 suno 생성 곡수 = 영상 길이(비용·길이 직접 제어) */}
          <TrackCountInput key={trackCount} current={trackCount} busy={busy} onApply={(n) => patch({ trackCount: n })} />
          {/* 채널 설정(#37) — 슬로건·소셜·AI 명시 */}
          <Link
            href="/music/settings"
            title="채널 설정(슬로건·소셜·AI 명시) — 공개 업로드 본문에 반영"
            className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
          >
            <Settings className="h-4 w-4" />
            채널 설정
          </Link>
          {/* 디자인 본부(#35-A) — PLAY LIST·Where 폰트/테두리 */}
          <Link
            href="/music/design"
            title="디자인 본부 — PLAY LIST·Where 폰트·크기·색·테두리"
            className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
          >
            <Palette className="h-4 w-4" />
            디자인 본부
          </Link>
          {/* 검토 대기 (백곰 캐릭터 시트 자리 — 보라 강조) */}
          <Link
            href="/music/queue"
            className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            <ClipboardList className="h-4 w-4" />
            검토 대기
            {queueCount > 0 && <span className="rounded-full bg-white/20 px-1.5 text-[10px] font-semibold">{queueCount}</span>}
          </Link>
          {/* 가동 토글 */}
          <button
            onClick={() => patch({ isActive: !isActive })}
            disabled={busy}
            aria-pressed={isActive}
            className={`flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition-all duration-200 disabled:opacity-60 ${
              isActive ? "border border-red-500/30 text-red-400 hover:bg-red-500/10" : "bg-emerald-600 text-white shadow-sm hover:opacity-90"
            }`}
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : isActive ? <Square className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            {isActive ? "중단" : "시작"}
          </button>
        </div>
      </div>

      {/* KPI 줄 — 백곰 1:1 (아이콘 + 라벨 / mono 큰 숫자) */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {cards.map((s) => (
          <div key={s.label} className="rounded-xl border border-border bg-card p-2.5">
            <div className="flex items-center gap-2 text-muted-foreground">
              <s.icon className="h-4 w-4" />
              <span className="text-xs">{s.label}</span>
            </div>
            <p className="mt-1 text-base font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
              {s.value}
            </p>
          </div>
        ))}
      </div>

      {/* 좌 트렌드 / 우 오늘콘텐츠 — 5:5 */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div className="[&>div]:h-full">
          <MusicTrendPanel />
        </div>
        <div className="[&>div]:h-full">
          <MusicQueuePreview />
        </div>
      </div>

      {/* 파이프라인 — 진행 중 작업 실시간 반영(#36) */}
      <MusicPipeline activeJobs={activeJobs} />

      {/* 최근 업로드 마퀴 */}
      <MusicMarquee />
    </div>
  )
}

// #40 곡수 입력창(1~100) — 숫자 입력 + [적용] + 예상(크레딧/비용/길이/렌더) 즉시 표시.
// 곡수↔길이 연동(#40): 영상 길이 = 곡 총 길이(약 곡당 4분). 정확한 예상시간은 #41 예정.
function TrackCountInput({ current, busy, onApply }: { current: number; busy: boolean; onApply: (n: number) => void }) {
  // current 변경 시 부모가 key={current} 로 재마운트 → 입력값 재초기화(setState-in-effect 회피).
  const [val, setVal] = useState(String(current))
  const n = Number(val)
  const valid = Number.isInteger(n) && n >= 1 && n <= 100
  const credits = valid ? n * 12 : 0
  const cost = (credits * 0.005).toFixed(2)
  const songMin = valid ? (n * 4).toFixed(0) : "0" // #40 곡당 ~4분(대략). 정확값은 #41.
  const renderMin = valid ? n : 0

  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium">
      <div className="flex items-center gap-1.5">
        <span className="text-muted-foreground">곡수</span>
        <input
          type="number"
          min={1}
          max={100}
          value={val}
          onChange={(e) => setVal(e.target.value)}
          className="h-7 w-14 rounded-md border border-border bg-background px-1.5 text-center text-xs text-foreground"
        />
        <span className="text-muted-foreground">곡</span>
        <button
          type="button"
          disabled={busy || !valid || n === current}
          onClick={() => valid && onApply(n)}
          className="rounded-md bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground hover:opacity-90 disabled:opacity-40"
        >
          적용
        </button>
      </div>
      {!valid ? (
        <span className="text-[10px] text-red-400">1~100 사이 숫자를 입력하세요</span>
      ) : (
        <span className="text-[10px] text-muted-foreground">
          예상: {credits} 크레딧 (~${cost}) · 영상 약 {songMin}분 · 렌더 약 {renderMin}분
        </span>
      )}
    </div>
  )
}
