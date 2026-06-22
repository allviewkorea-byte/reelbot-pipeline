"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import {
  Play,
  Square,
  Loader2,
  Clapperboard,
  Eye,
  BarChart3,
  Users,
  Video,
} from "lucide-react"
import { PLATFORM_BADGE, PLATFORM_LABELS, TRACK_BADGE, TRACK_LABELS } from "@/lib/channels"
import { BAEKGOM_CHANNEL_ID, DEFAULT_DAILY_CAP, clampDailyCap } from "@/lib/content-plan"
import { CHANNEL_STATUS_EVENT, type ChannelStatusDetail, type ChannelMode } from "@/lib/channel-status"
import { pollJobStatus } from "@/lib/api"
import { RecentVideosMarquee } from "@/components/dashboard/RecentVideosMarquee"
import { PipelineNodeGraph } from "@/components/dashboard/PipelineNodeGraph"
import { TrendPanel } from "@/components/dashboard/TrendPanel"
import { ContentCalendar } from "@/components/dashboard/ContentCalendar"

// 백곰의 실화보고서 = 유일 운영 채널(트랙 A, /sayeon 엔진). 채널 DB 레코드 없이 고정 표시.
// 관제 대시보드는 UI-2 채널 대시보드 골격(헤더+제어바+지표+최근영상)을 재사용(복제)한다.
const BAEKGOM = {
  name: "백곰의 실화보고서",
  platform: "youtube" as const,
  track: "auto" as const,
}

// 채널 통계 응답(/api/channel-stats). 값 없으면 null → 카드에 "—".
interface ChannelStats {
  subscriberCount: number | null
  viewCount: number | null
  videoCount: number | null
  averageViews: number | null
}

// 한국어 단위 포맷(만/억). null/undefined → "—"(가짜 숫자 금지). 실제 0 → "0".
function fmtCount(n: number | null | undefined): string {
  if (n == null) return "—"
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1).replace(/\.0$/, "")}억`
  if (n >= 10_000) return `${(n / 10_000).toFixed(1).replace(/\.0$/, "")}만`
  return n.toLocaleString("ko-KR")
}

export default function DashboardPage() {
  // 가동 상태(ON/OFF) — channel_status 저장값. 토글 1개로 제어, 헤더 뱃지·사이드바에 반영.
  // 실제 자동 업로드(스케줄러 연동)는 후속 작업. 지금은 상태 저장·표시까지.
  const [isActive, setIsActive] = useState(false)
  const [busy, setBusy] = useState(false)
  // 제작 진행 표시(가동 ON 시 화면 없이 트리거되는 흰곰 제작). 노드그래프와 별개의 버튼 표식.
  const [producing, setProducing] = useState(false)
  // 업로드 모드 — auto=공개 / semi(반자동)=비공개. 기본 semi(안전). 제작 시 privacy 결정.
  const [mode, setMode] = useState<ChannelMode>("semi")
  const [modeBusy, setModeBusy] = useState(false)
  // AI 합성 콘텐츠 표시 토글(유튜브 containsSyntheticMedia). 기본 off. 제작 시 업로드에 반영.
  const [syntheticMedia, setSyntheticMedia] = useState(false)
  const [synthBusy, setSynthBusy] = useState(false)
  // 하루 생산 개수(daily_cap, 1~3). 캘린더 슬롯·오늘의 콘텐츠·produce-due 캡을 동시 제어.
  const [dailyCap, setDailyCap] = useState(DEFAULT_DAILY_CAP)
  const [capBusy, setCapBusy] = useState(false)
  // 채널 KPI 통계(구독자·총조회수·영상수·평균). 로딩/실패/null → 카드 "—".
  const [stats, setStats] = useState<ChannelStats | null>(null)
  // 트렌드 패널 + 월간 계획서 공유 펼침 상태(짝으로 동시 펼침/접힘). 기본 접힘.
  const [panelExpanded, setPanelExpanded] = useState(false)
  const togglePanels = () => setPanelExpanded((v) => !v)

  // 마운트 시 채널 통계 로드(서버 라우트, YOUTUBE_API_KEY 서버 전용). 실패/미설정 → null 유지("—").
  useEffect(() => {
    let alive = true
    fetch("/api/channel-stats")
      .then((r) => r.json())
      .then((d) => {
        if (alive && d && !d.error) setStats(d as ChannelStats)
      })
      .catch(() => {
        /* 실패 → null 유지("—") */
      })
    return () => {
      alive = false
    }
  }, [])

  // 마운트 시 현재 상태 로드. setState 는 비동기 콜백에서만(effect 본문 직접 호출 회피).
  useEffect(() => {
    let alive = true
    fetch(`/api/channel-status?channelId=${BAEKGOM_CHANNEL_ID}`)
      .then((r) => r.json())
      .then((d) => {
        if (!alive) return
        setIsActive(Boolean(d?.isActive))
        setMode(d?.mode === "auto" ? "auto" : "semi")
        setSyntheticMedia(Boolean(d?.syntheticMedia))
        setDailyCap(clampDailyCap(d?.dailyCap))
      })
      .catch(() => {
        /* 실패 → 기본(OFF·반자동) 유지 */
      })
    return () => {
      alive = false
    }
  }, [])

  // '제작 중' 표시 = produce-due(스케줄)가 실제 제작할 때만. /api/jobs/active 를 주기
  // 폴링해 진행 중 job 이 있으면 표시(시작 버튼이 강제 제작하지 않으므로, 표시는 스케줄
  // 제작에만 반응한다).
  useEffect(() => {
    let alive = true
    let stop = () => {}
    const check = () => {
      fetch("/api/jobs/active")
        .then((r) => r.json())
        .then((d) => {
          if (!alive) return
          if (d && typeof d.job_id === "string" && (d.status === "running" || d.status === "pending")) {
            setProducing(true)
            stop()
            stop = pollJobStatus(d.job_id, (s) => {
              if (s.status === "completed" || s.status === "failed") setProducing(false)
            })
          } else {
            setProducing(false)
          }
        })
        .catch(() => {})
    }
    check()
    const timer = setInterval(check, 15000)
    return () => {
      alive = false
      clearInterval(timer)
      stop()
    }
  }, [])

  // 업로드 모드 토글(공개=auto↔비공개=semi). 저장만 — 사이드바와 무관해 이벤트는 발행 안 함.
  const toggleMode = async () => {
    if (modeBusy) return
    const next: ChannelMode = mode === "auto" ? "semi" : "auto"
    setModeBusy(true)
    try {
      const res = await fetch("/api/channel-status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channelId: BAEKGOM_CHANNEL_ID, mode: next }),
      })
      const d = await res.json()
      if (res.ok && d?.success) setMode(next)
    } catch {
      /* 실패 → 유지 */
    } finally {
      setModeBusy(false)
    }
  }

  // AI 표시 토글(ON↔OFF). 저장만. 제작 시 업로드 containsSyntheticMedia 에 반영(프록시 주입).
  const toggleSynthetic = async () => {
    if (synthBusy) return
    const next = !syntheticMedia
    setSynthBusy(true)
    try {
      const res = await fetch("/api/channel-status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channelId: BAEKGOM_CHANNEL_ID, syntheticMedia: next }),
      })
      const d = await res.json()
      if (res.ok && d?.success) setSyntheticMedia(next)
    } catch {
      /* 실패 → 유지 */
    } finally {
      setSynthBusy(false)
    }
  }

  // 하루 생산 개수 변경: daily_cap 저장 → 오늘 이후 미제작 날짜만 새 cap 으로 캘린더 재생성.
  const changeCap = async (next: number) => {
    if (capBusy || next === dailyCap) return
    const prev = dailyCap
    setDailyCap(next) // 낙관적
    setCapBusy(true)
    try {
      const res = await fetch("/api/channel-status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channelId: BAEKGOM_CHANNEL_ID, dailyCap: next }),
      })
      const d = await res.json()
      if (!res.ok || !d?.success) {
        setDailyCap(prev) // 실패 → 롤백
        return
      }
      // 미래 캘린더 재생성(과거·제작완료 보존). 실패해도 cap 저장은 유지.
      await fetch("/api/calendar/apply-cap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channelId: BAEKGOM_CHANNEL_ID, cap: next }),
      }).catch(() => {})
    } catch {
      setDailyCap(prev)
    } finally {
      setCapBusy(false)
    }
  }

  // 시작↔중단 토글 — 가동 상태(is_active)만 켜고/끈다.
  //  - 시작(OFF→ON): is_active 저장 + 사이드바 즉시 동기화 → 곧바로 "중단"/"가동 중".
  //    ★강제 즉시 제작 없음 — 실제 제작은 produce-due(스케줄)가 슬롯 시각에 수행한다.
  //  - 중단(ON→OFF): is_active OFF(스케줄 자연 정지). 진행 중 백그라운드 job 은 계속될 수 있음.
  const toggle = async () => {
    if (busy) return
    const next = !isActive
    setBusy(true)
    try {
      const res = await fetch("/api/channel-status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channelId: BAEKGOM_CHANNEL_ID, isActive: next }),
      })
      const d = await res.json()
      if (res.ok && d?.success) {
        setIsActive(next)
        const detail: ChannelStatusDetail = { channelId: BAEKGOM_CHANNEL_ID, isActive: next }
        window.dispatchEvent(new CustomEvent(CHANNEL_STATUS_EVENT, { detail }))
      }
    } catch {
      /* 실패 → 상태 유지 */
    } finally {
      setBusy(false)
    }
  }

  // KPI 카드 — 라벨/아이콘 고정, 값은 실데이터(없으면 "—"). 카드 디자인은 그대로.
  const cards = [
    { label: "구독자", icon: Users, value: fmtCount(stats?.subscriberCount) },
    { label: "총 조회수", icon: Eye, value: fmtCount(stats?.viewCount) },
    { label: "평균 조회수", icon: BarChart3, value: fmtCount(stats?.averageViews) },
    { label: "영상 수", icon: Video, value: fmtCount(stats?.videoCount) },
  ]

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-auto p-4 md:overflow-hidden">
      {/* 헤더 — 채널명+뱃지(왼쪽) / 사연 제작·가동 토글(오른쪽). NEXT UP 줄은 제거됨.
          모바일: 세로 스택(제목 줄 / 컨트롤 줄). 데스크탑(md+): 기존 가로 배치 그대로. */}
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0 pl-10 md:pl-0">
          <div className="flex flex-wrap items-center gap-2 md:flex-nowrap">
            <h1 className="text-lg font-semibold text-foreground truncate">{BAEKGOM.name}</h1>
            <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${PLATFORM_BADGE[BAEKGOM.platform]}`}>
              {PLATFORM_LABELS[BAEKGOM.platform]}
            </span>
            <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${TRACK_BADGE[BAEKGOM.track]}`}>
              {TRACK_LABELS[BAEKGOM.track]}
            </span>
            {/* 가동 상태 뱃지 — 토글/사이드바와 동일 상태. ON=emerald(맥동), OFF=muted */}
            <span
              className={`flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors duration-200 ${
                isActive ? "bg-emerald-500/15 text-emerald-400" : "bg-secondary/50 text-muted-foreground"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  isActive ? "bg-emerald-500 animate-pulse" : "bg-muted-foreground/50"
                }`}
              />
              {isActive ? "가동 중" : "대기 중"}
            </span>
          </div>
          <p className="mt-0.5 text-sm text-muted-foreground">운영 채널 관제 대시보드</p>
        </div>

        {/* 액션 — 공개/비공개 토글 + 캐릭터 시트 + 가동 시작↔중단 토글.
            모바일: 왼쪽 정렬 + 줄바꿈(넘침 방지, 버튼 축소 없음). 데스크탑: 기존 오른쪽 정렬. */}
        <div className="flex shrink-0 flex-wrap items-center justify-start gap-2 md:justify-end">
          {/* 공개/비공개 — 스케줄 제작(produce-due)의 유튜브 업로드 공개범위를 결정.
              공개=public / 비공개=private. (내부 저장 필드는 mode auto/semi 그대로.) */}
          <button
            onClick={toggleMode}
            disabled={modeBusy}
            role="switch"
            aria-checked={mode === "auto"}
            title="공개=유튜브 공개 업로드 / 비공개=비공개 업로드"
            className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium transition-colors hover:border-primary/40 disabled:opacity-60"
          >
            <span className={mode === "auto" ? "text-emerald-400" : "text-muted-foreground"}>
              {mode === "auto" ? "공개" : "비공개"}
            </span>
            <span
              className={`relative h-4 w-7 shrink-0 rounded-full transition-colors ${
                mode === "auto" ? "bg-emerald-600" : "bg-secondary"
              }`}
            >
              <span
                className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${
                  mode === "auto" ? "left-3.5" : "left-0.5"
                }`}
              />
            </span>
          </button>
          {/* AI 표시 — 유튜브 업로드 시 합성 콘텐츠(containsSyntheticMedia) 표시 ON/OFF.
              공개/비공개와 동일한 스위치 스타일 재사용. 제작 전 경로(시작·스케줄·테스트) 일괄 반영. */}
          <button
            onClick={toggleSynthetic}
            disabled={synthBusy}
            role="switch"
            aria-checked={syntheticMedia}
            title="유튜브 업로드에 'AI 합성 콘텐츠' 표시를 켜고/끕니다"
            className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium transition-colors hover:border-primary/40 disabled:opacity-60"
          >
            <span className={syntheticMedia ? "text-emerald-400" : "text-muted-foreground"}>
              AI 표시 {syntheticMedia ? "ON" : "OFF"}
            </span>
            <span
              className={`relative h-4 w-7 shrink-0 rounded-full transition-colors ${
                syntheticMedia ? "bg-emerald-600" : "bg-secondary"
              }`}
            >
              <span
                className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${
                  syntheticMedia ? "left-3.5" : "left-0.5"
                }`}
              />
            </span>
          </button>
          {/* 하루 생산 개수(daily_cap) — 캘린더 슬롯·오늘의 콘텐츠·produce-due 캡을 동시 제어.
              공개/비공개·AI 표시 버튼과 같은 토큰 스타일의 1/2/3 세그먼트 토글(zero-diff, 새 토큰 0). */}
          <div
            className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium"
            title="하루에 자동 게시할 영상 개수(캘린더·스케줄에 일괄 반영)"
          >
            <span className="text-muted-foreground">하루</span>
            <div className="inline-flex rounded-md border border-border bg-background p-0.5">
              {[1, 2, 3].map((n) => {
                const active = dailyCap === n
                return (
                  <button
                    key={n}
                    type="button"
                    onClick={() => changeCap(n)}
                    disabled={capBusy}
                    aria-pressed={active}
                    className={`rounded px-2 py-0.5 text-xs font-medium transition-colors disabled:opacity-50 ${
                      active
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {n}
                  </button>
                )
              })}
            </div>
            <span className="text-muted-foreground">개</span>
          </div>
          {/* 캐릭터 시트 관리 화면(/cast) 진입 — 8캐스트 시트 생성·확정 + 테스트 영상.
              (/sayeon 제작 엔진은 무수정·유지. 메인 진입에서만 /cast 로 변경.) */}
          <Link
            href="/cast"
            className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            <Clapperboard className="h-4 w-4" />
            캐릭터 시트
          </Link>
          {/* 가동 토글 — OFF→[▶ 시작](emerald), ON→[■ 중단](red). 상태 저장(channel_status).
              #112 가동상태 로직(GET/POST + 사이드바 동기화) 그대로 유지. */}
          <button
            onClick={toggle}
            disabled={busy}
            aria-pressed={isActive}
            className={`flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition-all duration-200 disabled:opacity-60 ${
              isActive
                ? "border border-red-500/30 text-red-400 hover:bg-red-500/10"
                : "bg-emerald-600 text-white shadow-sm hover:opacity-90"
            }`}
          >
            {producing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : isActive ? (
              <Square className="h-4 w-4" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            {producing ? "제작 중…" : isActive ? "중단" : "시작"}
          </button>
        </div>
      </div>

      {/* 채널 KPI 줄 — /api/channel-stats 실데이터(구독자·총조회수·평균·영상수) */}
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

      {/* 좌우 한 줄 — 왼쪽 트렌드 분석 / 오른쪽 월간계획서·오늘콘텐츠. 정확히 5:5(반반). 같은 높이.
          펼침 상태는 공유(panelExpanded): 어느 버튼을 눌러도 둘 다 동시에 펼침/접힘. */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {/* 트렌드 분석(왼쪽) — 빈 그릇(준비 중). 실제 엔진은 다음 PR. (가짜 데이터 없음) */}
        <div className="[&>div]:h-full">
          <TrendPanel open={panelExpanded} onToggle={togglePanels} />
        </div>
        {/* 콘텐츠 캘린더(오른쪽) — 접힘=오늘의 콘텐츠(3슬롯), 펼침=월간 계획서 */}
        <div className="[&>div]:h-full">
          <ContentCalendar monthOpen={panelExpanded} onToggleMonth={togglePanels} />
        </div>
      </div>

      {/* 파이프라인 노드그래프 — 활성 job 실시간 점등(UI-4a). /api/jobs/active 폴링. */}
      <PipelineNodeGraph />

      {/* 최근 업로드 영상 — 플랫폼 탭 + 우→좌 자동 마퀴(UI-3). 더미 데이터, 실연동은 UI-3b. */}
      <RecentVideosMarquee />
    </div>
  )
}
