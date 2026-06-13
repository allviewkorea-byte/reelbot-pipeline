"use client"

import Link from "next/link"
import {
  Play,
  Pause,
  Square,
  Clapperboard,
  Eye,
  DollarSign,
  Users,
  Video,
  Film,
} from "lucide-react"
import { PLATFORM_BADGE, PLATFORM_LABELS, TRACK_BADGE, TRACK_LABELS } from "@/lib/channels"

// 백곰의 실화보고서 = 유일 운영 채널(트랙 A, /sayeon 엔진). 채널 DB 레코드 없이 고정 표시.
// 관제 대시보드는 UI-2 채널 대시보드 골격(헤더+제어바+지표+최근영상)을 재사용(복제)한다.
const BAEKGOM = {
  name: "백곰의 실화보고서",
  platform: "youtube" as const,
  track: "auto" as const,
  status: "가동 중",
}

// 월간 지표 — 백곰 실데이터 연동 전이라 플레이스홀더("—"). UI-5 캘린더/연동에서 연결.
const METRICS = [
  { label: "월 조회수", value: "—", icon: Eye },
  { label: "월 수익", value: "—", icon: DollarSign },
  { label: "구독자", value: "—", icon: Users },
  { label: "평균 조회수", value: "—", icon: Video },
]

export default function DashboardPage() {
  return (
    <div className="flex flex-1 flex-col gap-5 overflow-auto p-6">
      {/* 헤더 — 채널명 + 플랫폼/트랙/상태 뱃지 (UI-2 헤더 재사용) */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-foreground truncate">{BAEKGOM.name}</h1>
            <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${PLATFORM_BADGE[BAEKGOM.platform]}`}>
              {PLATFORM_LABELS[BAEKGOM.platform]}
            </span>
            <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${TRACK_BADGE[BAEKGOM.track]}`}>
              {TRACK_LABELS[BAEKGOM.track]}
            </span>
            <span className="shrink-0 rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs font-medium text-emerald-400">
              {BAEKGOM.status}
            </span>
          </div>
          <p className="mt-0.5 text-sm text-muted-foreground">운영 채널 관제 대시보드</p>
        </div>
      </div>

      {/* 제어 바 — NEXT UP + 사연 제작 열기(실제 진입) + (UI 전용) 시작/일시정지/중단 */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-4">
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
          {/* 아래 3개는 UI 전용 — 실제 동작(백엔드 호출)은 후속 PR */}
          <button
            onClick={() => console.log("[baekgom-control] 시작 — 동작은 후속 PR")}
            className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
          >
            <Play className="h-4 w-4" /> 시작
          </button>
          <button
            onClick={() => console.log("[baekgom-control] 일시정지 — 동작은 후속 PR")}
            className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-secondary/30"
          >
            <Pause className="h-4 w-4" /> 일시정지
          </button>
          <button
            onClick={() => console.log("[baekgom-control] 중단 — 동작은 후속 PR")}
            className="flex items-center gap-1.5 rounded-lg border border-red-500/30 px-3 py-2 text-sm font-medium text-red-400 transition-colors hover:bg-red-500/10"
          >
            <Square className="h-4 w-4" /> 중단
          </button>
        </div>
      </div>

      {/* 월간 지표 줄 (UI-2 지표 재사용, 값은 플레이스홀더) */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {METRICS.map((s) => (
          <div key={s.label} className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center gap-2 text-muted-foreground">
              <s.icon className="h-4 w-4" />
              <span className="text-xs">{s.label}</span>
            </div>
            <p className="mt-2 text-xl font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
              {s.value}
            </p>
          </div>
        ))}
      </div>

      {/* 최근 영상 — 가로 스크롤 카드 자리(마퀴 자동스크롤·플랫폼 탭은 UI-3, 실데이터 연동 후속) */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h2 className="mb-3 text-sm font-semibold text-foreground">최근 영상</h2>
        <div className="flex gap-3 overflow-x-auto pb-1">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="w-44 shrink-0 rounded-lg border border-border/60 p-3">
              <div className="flex h-24 w-full items-center justify-center rounded-md bg-secondary/50">
                <Film className="h-5 w-5 text-muted-foreground" />
              </div>
              <p className="mt-2 truncate text-sm text-muted-foreground">데이터 연동 예정</p>
              <p className="text-xs text-muted-foreground">—</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
