"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import {
  Play,
  Square,
  Clapperboard,
  Eye,
  DollarSign,
  Users,
  Video,
} from "lucide-react"
import { PLATFORM_BADGE, PLATFORM_LABELS, TRACK_BADGE, TRACK_LABELS } from "@/lib/channels"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"
import { CHANNEL_STATUS_EVENT, type ChannelStatusDetail } from "@/lib/channel-status"
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

// 월간 지표 — 백곰 실데이터 연동 전이라 플레이스홀더("—"). UI-5 캘린더/연동에서 연결.
const METRICS = [
  { label: "월 조회수", value: "—", icon: Eye },
  { label: "월 수익", value: "—", icon: DollarSign },
  { label: "구독자", value: "—", icon: Users },
  { label: "평균 조회수", value: "—", icon: Video },
]

export default function DashboardPage() {
  // 가동 상태(ON/OFF) — channel_status 저장값. 토글 1개로 제어, 헤더 뱃지·사이드바에 반영.
  // 실제 자동 업로드(스케줄러 연동)는 후속 작업. 지금은 상태 저장·표시까지.
  const [isActive, setIsActive] = useState(false)
  const [busy, setBusy] = useState(false)

  // 마운트 시 현재 상태 로드. setState 는 비동기 콜백에서만(effect 본문 직접 호출 회피).
  useEffect(() => {
    let alive = true
    fetch(`/api/channel-status?channelId=${BAEKGOM_CHANNEL_ID}`)
      .then((r) => r.json())
      .then((d) => {
        if (alive) setIsActive(Boolean(d?.isActive))
      })
      .catch(() => {
        /* 실패 → 기본 OFF 유지 */
      })
    return () => {
      alive = false
    }
  }, [])

  // 시작↔중단 토글: 저장(POST) 성공 시 상태 갱신 + 사이드바 즉시 동기화 이벤트 발행.
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

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-hidden p-4">
      {/* 헤더 — 채널명 + 플랫폼/트랙/상태 뱃지 (UI-2 헤더 재사용) */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
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
      </div>

      {/* 제어 바 — NEXT UP + 사연 제작 열기(실제 진입) + 가동 시작↔중단 토글 */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-3">
        <div className="min-w-0">
          {/* NEXT UP — 스케줄 타임스탬프 미연동 → 플레이스홀더(UI-5에서 연결) */}
          <p className="text-xs text-muted-foreground">NEXT UP</p>
          <p className="text-sm font-semibold text-foreground">다음 업로드 —</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* 백곰의 실제 제작 진입점: /sayeon 으로만 이동(파라미터 없음, CLAUDE.md 2단계 원칙) */}
          <Link
            href="/sayeon"
            className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            <Clapperboard className="h-4 w-4" />
            사연 제작 열기
          </Link>
          {/* 가동 토글 — OFF→[▶ 시작](emerald), ON→[■ 중단](red). 상태 저장(channel_status).
              실제 자동 업로드 연결은 후속(스케줄러). 색/아이콘/라벨이 상태따라 부드럽게 전환. */}
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
            {isActive ? <Square className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            {isActive ? "중단" : "시작"}
          </button>
        </div>
      </div>

      {/* 월간 지표 줄 (UI-2 지표 재사용, 값은 플레이스홀더) */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {METRICS.map((s) => (
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

      {/* 파이프라인 노드그래프 — 활성 job 실시간 점등(UI-4a). /api/jobs/active 폴링. */}
      <PipelineNodeGraph />

      {/* 트렌드 분석 — 빈 그릇(준비 중). 실제 엔진은 다음 PR. (가짜 데이터 없음) */}
      <TrendPanel />

      {/* 콘텐츠 캘린더 — 기본 '오늘의 콘텐츠'(3슬롯), 전체 보기=월간. 마퀴 바로 위. */}
      <ContentCalendar />

      {/* 최근 업로드 영상 — 플랫폼 탭 + 우→좌 자동 마퀴(UI-3). 더미 데이터, 실연동은 UI-3b. */}
      <RecentVideosMarquee />
    </div>
  )
}
