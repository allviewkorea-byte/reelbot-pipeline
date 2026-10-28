"use client"

import { Suspense, useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { Users, Eye, BarChart3, Video, ClipboardList, Play, Square, Loader2, Settings, Palette, Music2, UserRound, Clapperboard } from "lucide-react"
import { PLATFORM_BADGE, PLATFORM_LABELS, TRACK_BADGE, TRACK_LABELS } from "@/lib/channels"
import {
  AUTO_RUN_CHANNELS, MUSIC_CHANNELS, WORKOUT_CHANNEL_ID, channelParam, defaultPublishHours, fmtCount, normalizePublishHours,
  estimateProductionTime, fmtMinutes, resolveMusicChannel, withChannel, type MusicMetrics,
} from "@/lib/music"
import { useSearchParams } from "next/navigation"
import { MusicPipeline } from "@/components/music/MusicPipeline"
import { MusicMarquee } from "@/components/music/MusicMarquee"
import { MusicTrendPanel } from "@/components/music/MusicTrendPanel"
import { MusicQueuePreview } from "@/components/music/MusicQueuePreview"
import { MusicStatusBoard, MusicStatusLight, useMusicSummary } from "@/components/music/MusicStatusBoard"
import type { MusicJob } from "@/lib/music-jobs"
import { DailyReportCard } from "@/components/system/DailyReportCard"

interface ChannelStatus {
  isActive: boolean
  mode: "auto" | "semi"
  syntheticMedia: boolean
  dailyCap: number
  trackCount: number
}

const DEFAULT_STATUS: ChannelStatus = { isActive: false, mode: "semi", syntheticMedia: false, dailyCap: 3, trackCount: 1 }

export default function MusicDashboardPage() {
  return (
    <Suspense fallback={null}>
      <MusicDashboardPageInner />
    </Suspense>
  )
}

function MusicDashboardPageInner() {
  const searchParams = useSearchParams()
  // 선택된 채널 — URL 쿼리가 단일 진실. 미지정·미등록 → where(회귀 0).
  const channel = resolveMusicChannel(searchParams.get("channel"))
  const chInfo = MUSIC_CHANNELS[channel]
  const [status, setStatus] = useState<ChannelStatus>(DEFAULT_STATUS)
  const [stats, setStats] = useState<MusicMetrics | null>(null)
  const [queueCount, setQueueCount] = useState(0)
  const [busy, setBusy] = useState(false)
  const [activeJobs, setActiveJobs] = useState<MusicJob[]>([])

  // 채널별 상태(PR-2a) — 가동·공개·AI 표시·하루 개수·곡수를 **지금 화면 채널** 행에서 읽고 쓴다.
  // where 화면은 channel === "rooftop_music"(기존 MUSIC_CHANNEL_ID)라 요청이 이전과 바이트 동일.
  const loadStatus = useCallback(() => {
    fetch(`/api/channel-status?channelId=${channel}`)
      .then((r) => r.json())
      .then((d) => {
        if (d?.success) setStatus({ isActive: d.isActive, mode: d.mode, syntheticMedia: d.syntheticMedia, dailyCap: d.dailyCap, trackCount: d.trackCount })
      })
      .catch(() => {})
  }, [channel])

  useEffect(() => {
    loadStatus()
    const _cp = channelParam(channel)
    fetch(`/api/music/metrics${_cp ? `?${_cp}` : ""}`).then((r) => r.json()).then(setStats).catch(() => setStats(null))
    fetch(`/api/music/queue${_cp ? `?${_cp}` : ""}`).then((r) => r.json()).then((d) => setQueueCount(Array.isArray(d?.queue) ? d.queue.length : 0)).catch(() => {})
  }, [loadStatus, channel])

  // #36 운영 가시성 — 진행 중 작업 폴링(4초) → 파이프라인 실시간 시각화.
  useEffect(() => {
    let alive = true
    const tick = () => {
      fetch(`/api/music/jobs/active${channelParam(channel) ? `?${channelParam(channel)}` : ""}`)
        .then((r) => r.json())
        .then((d) => { if (alive) setActiveJobs(Array.isArray(d?.jobs) ? d.jobs : []) })
        .catch(() => {})
    }
    tick()
    const id = setInterval(tick, 4000)
    return () => { alive = false; clearInterval(id) }
  }, [channel])

  const patch = useCallback(
    async (body: Partial<{ isActive: boolean; mode: string; syntheticMedia: boolean; dailyCap: number; trackCount: number }>) => {
      setBusy(true)
      setStatus((s) => ({ ...s, ...body } as ChannelStatus))
      try {
        const res = await fetch("/api/channel-status", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ channelId: channel, ...body }),
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
    [loadStatus, channel],
  )

  const { isActive, mode, syntheticMedia, dailyCap, trackCount } = status
  // 메인 상태판 요약(1분 갱신) — 상태등·알림은 휴대폰에선 제목 바로 아래, PC 에선 헤더 아래에 그린다.
  const summary = useMusicSummary(channel)
  const isPublic = mode === "auto"

  const cards = [
    { label: "구독자", icon: Users, value: fmtCount(stats?.subscriberCount) },
    { label: "총 조회수", icon: Eye, value: fmtCount(stats?.viewCount) },
    { label: "평균 조회수", icon: BarChart3, value: fmtCount(stats?.averageViews) },
    { label: "영상 수", icon: Video, value: fmtCount(stats?.videoCount) },
  ]

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-auto p-4">
      {/* 오늘의 점검(09:30 자동, 펼치기) — 2026-10-28 */}
      <div className="pl-10 md:pl-0"><DailyReportCard compact /></div>
      {/* 헤더 — 채널명+뱃지 / 토글들. 백곰 레이아웃 1:1 */}
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0 pl-10 md:pl-0">
          <div className="flex items-start justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2 md:flex-nowrap">
              <h1 className="truncate text-lg font-semibold text-foreground">{chInfo.name}</h1>
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
              href={withChannel("/music/settings", channel)}
              title="채널 설정(슬로건·소셜·AI 명시) — 공개 업로드 본문에 반영"
              className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground md:hidden"
            >
              <Settings className="h-4 w-4" />
              채널 설정
            </Link>
          </div>
          <p className="mt-0.5 text-sm text-muted-foreground">운영 채널 관제 대시보드</p>
        </div>

        {/* 휴대폰: 상태등·알림을 설정 버튼보다 위에(3초 안에 보이게). PC 는 헤더 아래 같은 컴포넌트. */}
        <MusicStatusLight {...summary} className="flex md:hidden" />

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
          {/* 공개 시각(PR-2a) — 자동 회차 채널(운동)만. where 화면엔 없다. */}
          {AUTO_RUN_CHANNELS.includes(channel) && <PublishHoursInput key={channel} channel={channel} dailyCap={dailyCap} />}
          {/* 검토 대기 — 공개 시각 옆 빈자리(대표 요청 2026-10-19). 네비 그룹에서 옮김 */}
          <Link
            href={withChannel("/music/queue", channel)}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            <ClipboardList className="h-4 w-4" />
            검토 대기
            {queueCount > 0 && <span className="rounded-full bg-white/20 px-1.5 text-[10px] font-semibold">{queueCount}</span>}
          </Link>
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
            href={withChannel("/music/settings", channel)}
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
            href={withChannel("/music/design", channel)}
            title="디자인 본부 — PLAY LIST·Where 폰트·크기·색·테두리"
            className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
          >
            <Palette className="h-4 w-4" />
            디자인 본부
          </Link>
          {/* 음원 라이브러리(#48) — 적립곡 큐레이션 → 선택 영상 만들기 */}
          <Link
            href={withChannel("/music/library", channel)}
            title="음원 라이브러리 — 적립곡 미리듣기·선택 → Suno 없이 바로 영상 만들기"
            className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
          >
            <Music2 className="h-4 w-4" />
            음원 라이브러리
          </Link>
          {/* 쇼츠 캐릭터 시트 — 운동 채널 전용(2주 몸만들기 챌린지 실사 캐스트) */}
          {channel === WORKOUT_CHANNEL_ID && (
            <Link
              href={withChannel("/shorts/cast", channel)}
              title="쇼츠 캐릭터 시트 — 챌린지 쇼츠 주인공(실사) 8장 생성·확정"
              className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
            >
              <UserRound className="h-4 w-4" />
              쇼츠 캐릭터
            </Link>
          )}
          {/* 쇼츠 제작(hero 형식 A) — 운동 채널 전용, 테스트는 미리보기만 */}
          {channel === WORKOUT_CHANNEL_ID && (
            <Link
              href={withChannel("/shorts/hero", channel)}
              title="쇼츠 제작 — 형식 A 원테이크 테스트·미리보기·곡 분석"
              className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
            >
              <Clapperboard className="h-4 w-4" />
              쇼츠 제작
            </Link>
          )}
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

      {/* 상태판 — (PC 상태등·알림) 오늘 회차·숫자 4개·최근 7회차. 기존 KPI 는 숫자 카드 아래 한 줄로. */}
      <MusicStatusLight {...summary} className="hidden md:flex" />
      <MusicStatusBoard
        key={`s-${channel}`}
        data={summary.data}
        afterNumbers={
          <div className="grid grid-cols-4 gap-2">
            {cards.map((s) => (
              <div key={s.label} className="flex min-w-0 items-center gap-1.5 rounded-lg border border-border bg-card px-2 py-1.5">
                <s.icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <span className="hidden truncate text-xs text-muted-foreground sm:inline">{s.label}</span>
                <span className="ml-auto truncate text-xs font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }} title={s.label}>
                  {s.value}
                </span>
              </div>
            ))}
          </div>
        }
      />

      {/* 기존 요소(아래로) — 진행 중 파이프라인 → 검토 대기 미리보기 → 트렌드 → 최근 업로드 마퀴 */}
      <MusicPipeline activeJobs={activeJobs} />

      <MusicQueuePreview key={`q-${channel}`} channel={channel} />

      <MusicTrendPanel channel={channel} />

      {/* 최근 업로드 마퀴 */}
      <MusicMarquee key={channel} channel={channel} />
    </div>
  )
}

// #41 곡수 입력창(1~100) — 숫자 입력 + [적용] + 예상 영상 길이·제작 시간·크레딧(접기/펼치기).
// estimateProductionTime(클라이언트 계산, API 호출 없음)으로 곡수↔길이(#40) 반영.
// 자동 회차 공개 시각(시 단위 2개, 기본 운동 06·18, where 08·21). 분은 백엔드가 매일·회차마다 랜덤으로 정한다.
// 제작은 공개 120분 전에 시작해 유튜브 예약 공개(publishAt)로 올린다. 하루 개수만큼 앞에서부터 쓴다.
function PublishHoursInput({ channel, dailyCap }: { channel: string; dailyCap: number }) {
  const [saved, setSaved] = useState<number[] | null>(null)
  const [vals, setVals] = useState<string[]>(defaultPublishHours(channel).map(String))
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let alive = true
    fetch(`/api/music/publish-hours?channelId=${encodeURIComponent(channel)}`)
      .then((r) => r.json())
      .then((d) => {
        if (!alive || !d?.success) return
        const h = normalizePublishHours(d.hours, channel)
        setSaved(h)
        const dh = defaultPublishHours(channel)
        setVals([String(h[0] ?? dh[0]), String(h[1] ?? dh[1])])
      })
      .catch(() => {})
    return () => { alive = false }
  }, [channel])

  const nums = vals.map((v) => Number(v))
  const valid = nums.every((n) => Number.isInteger(n) && n >= 0 && n <= 23) && nums[0] !== nums[1]
  const next = valid ? normalizePublishHours(nums, channel) : null
  const changed = next !== null && JSON.stringify(next) !== JSON.stringify(saved)

  const save = async () => {
    if (!next) return
    setSaving(true)
    try {
      const res = await fetch("/api/music/publish-hours", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channelId: channel, hours: next }),
      })
      const d = await res.json()
      if (!d?.success) throw new Error(d?.error || "저장 실패")
      setSaved(normalizePublishHours(d.hours, channel))
      toast.success(`공개 시각 저장: ${normalizePublishHours(d.hours, channel).map((h) => `${h}시대`).join(" · ")}`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "저장 실패")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium"
      title={`자동 회차 공개 시각(분은 매일 랜덤). 제작은 2시간 전 시작, 유튜브 예약 공개. 하루 ${dailyCap}개 → 앞에서부터 ${Math.min(dailyCap, 2)}개 사용`}
    >
      <span className="text-muted-foreground">공개</span>
      {vals.map((v, i) => (
        <input
          key={i}
          type="number"
          min={0}
          max={23}
          value={v}
          aria-label={`공개 시각 ${i + 1}`}
          onChange={(e) => setVals((p) => p.map((x, j) => (j === i ? e.target.value : x)))}
          className="h-7 w-11 rounded-md border border-border bg-background px-1 text-center text-xs text-foreground"
        />
      ))}
      <span className="text-muted-foreground">시대</span>
      <button
        type="button"
        disabled={saving || !changed}
        onClick={save}
        className="rounded-md bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground hover:opacity-90 disabled:opacity-40"
      >
        저장
      </button>
    </div>
  )
}

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
