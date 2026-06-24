"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { Users, Eye, BarChart3, Video, ClipboardList, Play, Square, Loader2, Settings, Palette, Music2 } from "lucide-react"
import { PLATFORM_BADGE, PLATFORM_LABELS, TRACK_BADGE, TRACK_LABELS } from "@/lib/channels"
import { MUSIC_CHANNEL_ID, MUSIC_CHANNEL_NAME, fmtCount, estimateProductionTime, fmtMinutes, type MusicMetrics } from "@/lib/music"
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
          <div className="flex items-start justify-between gap-2">
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
            {/* #51-fix 모바일 전용: 채널 설정을 제목 옆(우)으로. PC 는 아래 툴바에 있음. */}
            <Link
              href="/music/settings"
              title="채널 설정(슬로건·소셜·AI 명시) — 공개 업로드 본문에 반영"
              className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground md:hidden"
            >
              <Settings className="h-4 w-4" />
              채널 설정
            </Link>
          </div>
          <p className="mt-0.5 text-sm text-muted-foreground">운영 채널 관제 대시보드</p>
        </div>

        {/* #51-fix 모바일: 토글행 / 곡수+시작행 / 네비행으로 세로 스택. PC(md:contents): 기존 우측 정렬 wrap 그대로. */}
        <div className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center md:justify-end md:gap-2">
          {/* 토글 그룹 — 공개/AI/하루 (모바일 1행, PC contents) */}
          <div className="flex flex-wrap items-center gap-2 md:contents">
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
          </div>{/* /토글 그룹 */}

          {/* 곡수 + 시작(모바일) — 같은 행(곡수 좌 / 시작 우). 예상시간은 곡수 아래. PC contents. */}
          <div className="flex items-start justify-between gap-2 md:contents">
            {/* 곡수 입력창 1~100 (#40) — 영상 1개당 suno 생성 곡수 = 영상 길이(비용·길이 직접 제어) */}
            <TrackCountInput key={trackCount} current={trackCount} busy={busy} onApply={(n) => patch({ trackCount: n })} />
            {/* #51-fix 모바일 전용 시작/중단 — PC 는 툴바 끝(가동 토글)에 있음 */}
            <button
              onClick={() => patch({ isActive: !isActive })}
              disabled={busy}
              aria-pressed={isActive}
              className={`flex shrink-0 items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition-all duration-200 disabled:opacity-60 md:hidden ${
                isActive ? "border border-red-500/30 text-red-400 hover:bg-red-500/10" : "bg-emerald-600 text-white shadow-sm hover:opacity-90"
              }`}
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : isActive ? <Square className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              {isActive ? "중단" : "시작"}
            </button>
          </div>

          {/* 채널 설정(#37) — PC 전용(모바일은 제목 옆) */}
          <Link
            href="/music/settings"
            title="채널 설정(슬로건·소셜·AI 명시) — 공개 업로드 본문에 반영"
            className="hidden items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground md:flex"
          >
            <Settings className="h-4 w-4" />
            채널 설정
          </Link>
          {/* 네비 그룹 — 디자인본부/음원라이브러리/검토대기 (모바일 1행, PC contents) */}
          <div className="flex flex-wrap items-center gap-2 md:contents">
          {/* 디자인 본부(#35-A) — PLAY LIST·Where 폰트/테두리 */}
          <Link
            href="/music/design"
            title="디자인 본부 — PLAY LIST·Where 폰트·크기·색·테두리"
            className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
          >
            <Palette className="h-4 w-4" />
            디자인 본부
          </Link>
          {/* 음원 라이브러리(#48) — 적립곡 큐레이션 → 선택 영상 만들기 */}
          <Link
            href="/music/library"
            title="음원 라이브러리 — 적립곡 미리듣기·선택 → Suno 없이 바로 영상 만들기"
            className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
          >
            <Music2 className="h-4 w-4" />
            음원 라이브러리
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
          </div>{/* /네비 그룹 */}
          {/* 가동 토글 — PC 전용(모바일은 곡수 옆에 있음) */}
          <button
            onClick={() => patch({ isActive: !isActive })}
            disabled={busy}
            aria-pressed={isActive}
            className={`hidden items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition-all duration-200 disabled:opacity-60 md:flex ${
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

// #41 곡수 입력창(1~100) — 숫자 입력 + [적용] + 예상 영상 길이·제작 시간·크레딧(접기/펼치기).
// estimateProductionTime(클라이언트 계산, API 호출 없음)으로 곡수↔길이(#40) 반영.
function TrackCountInput({ current, busy, onApply }: { current: number; busy: boolean; onApply: (n: number) => void }) {
  // current 변경 시 부모가 key={current} 로 재마운트 → 입력값 재초기화(setState-in-effect 회피).
  const [val, setVal] = useState(String(current))
  const [open, setOpen] = useState(false)
  const n = Number(val)
  const valid = Number.isInteger(n) && n >= 1 && n <= 100
  const est = valid ? estimateProductionTime(n) : null

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
      {!est ? (
        <span className="text-[10px] text-red-400">1~100 사이 숫자를 입력하세요</span>
      ) : (
        <div className="flex flex-col gap-0.5 text-[10px] text-muted-foreground">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
            <span>📹 영상 {fmtMinutes(est.videoMinutes)}</span>
            <span>⏱️ 제작 {fmtMinutes(est.totalMinutes)}</span>
            <span>💰 {est.credits} 크레딧 (~${est.costUsd.toFixed(2)})</span>
            <button type="button" onClick={() => setOpen((o) => !o)} className="text-primary hover:underline">
              {open ? "접기" : "세부"}
            </button>
          </div>
          {open && (
            <div className="flex flex-col gap-px pl-3 text-muted-foreground/80">
              <span>└ Suno 생성 {fmtMinutes(est.sunoMinutes)}</span>
              <span>└ 믹스 {fmtMinutes(est.mixMinutes)}</span>
              <span>└ 렌더 {fmtMinutes(est.renderMinutes)}</span>
              <span>└ 업로드 {fmtMinutes(est.uploadMinutes)}</span>
              {n >= 3 && <span className="text-amber-500">※ 3곡 이상은 분할 렌더(#43) 전까지 타임아웃 가능</span>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
