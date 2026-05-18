"use client"

import { CheckCircle2, Loader2, Clock, CalendarDays, Terminal } from "lucide-react"

// ── Mock data ─────────────────────────────────────────────────────
const BIG_STATS = [
  { value: "24/7", label: "무중단 운영", mono: true },
  { value: "3편", label: "하루 자동 발행", mono: true },
  { value: "94%", label: "자동화율", mono: true, pct: 94 },
]

const TODAY_ITEMS = [
  {
    status: "done" as const,
    title: "시나리오 생성 완료",
    time: "오전 6:00",
    detail: "방콕 왓아룬 24장면",
  },
  {
    status: "done" as const,
    title: "영상 제작 완료",
    time: "오전 6:42",
    detail: "4분 영상 합성",
  },
  {
    status: "running" as const,
    title: "유튜브 업로드 중",
    time: "오전 9:00 예약",
    detail: "잔여 2시간",
  },
  {
    status: "waiting" as const,
    title: "다음 영상 시나리오 대기",
    time: "오후 1:00 시작 예정",
    detail: "",
  },
]

const SCHEDULE = [
  { time: "오전 6시", task: "시나리오 생성 시작" },
  { time: "오전 9시", task: "영상 업로드" },
  { time: "오후 1시", task: "다음 영상 시작" },
  { time: "자정", task: "일일 리포트 생성" },
]

const LOGS = [
  { t: "09:14", msg: "Seedance S18 렌더링 완료" },
  { t: "09:11", msg: "도쿄 시나리오 S12 작성 중" },
  { t: "09:08", msg: "캐릭터 이미지 24장 생성 완료" },
  { t: "09:00", msg: "파이프라인 자동 시작" },
  { t: "08:45", msg: "어제 영상 3편 업로드 완료" },
  { t: "08:30", msg: "분석 인사이트 업데이트" },
]

// ── Sub-components ────────────────────────────────────────────────
function StatusIcon({ status }: { status: "done" | "running" | "waiting" }) {
  if (status === "done") return <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
  if (status === "running") return <Loader2 className="h-4 w-4 shrink-0 animate-spin text-amber-400" />
  return <Clock className="h-4 w-4 shrink-0 text-muted-foreground/50" />
}

function StatusBadge({ status }: { status: "done" | "running" | "waiting" }) {
  if (status === "done")
    return <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-400">완료</span>
  if (status === "running")
    return <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-400">진행 중</span>
  return <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground">대기</span>
}

// ── Page ──────────────────────────────────────────────────────────
export default function AutomationPage() {
  return (
    <div className="flex flex-1 flex-col gap-5 overflow-auto p-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-foreground">100% 자동화</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          자는 동안에도 채널이 성장합니다
        </p>
      </div>

      {/* Big stats */}
      <div className="grid grid-cols-3 gap-4">
        {BIG_STATS.map((s) => (
          <div key={s.label} className="rounded-xl border border-border bg-card p-5">
            <p
              className="text-4xl font-bold text-foreground"
              style={{ fontFamily: "var(--font-geist-mono)" }}
            >
              {s.value}
            </p>
            <p className="mt-1.5 text-xs text-muted-foreground">{s.label}</p>
            {s.pct !== undefined && (
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-secondary">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${s.pct}%` }}
                />
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Today status */}
      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-foreground">오늘의 자동화 현황</h2>
          <span
            className="text-xs text-muted-foreground"
            style={{ fontFamily: "var(--font-geist-mono)" }}
          >
            09:14
          </span>
        </div>
        <div>
          {TODAY_ITEMS.map((item, i) => (
            <div
              key={i}
              className="flex items-start gap-3 border-b border-border/40 px-4 py-3 last:border-b-0"
            >
              <StatusIcon status={item.status} />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-foreground">{item.title}</p>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  {item.time}{item.detail ? ` · ${item.detail}` : ""}
                </p>
              </div>
              <StatusBadge status={item.status} />
            </div>
          ))}
        </div>
      </div>

      {/* Bottom row */}
      <div className="grid grid-cols-2 gap-4">
        {/* Schedule */}
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="mb-3 flex items-center gap-2">
            <CalendarDays className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold text-foreground">자동 스케줄</h2>
          </div>
          <div className="flex flex-col gap-2.5">
            {SCHEDULE.map((s, i) => (
              <div key={i} className="flex items-center gap-3">
                <span
                  className="w-16 shrink-0 text-xs font-medium text-primary"
                  style={{ fontFamily: "var(--font-geist-mono)" }}
                >
                  {s.time}
                </span>
                <div className="h-px flex-1 border-t border-dashed border-border" />
                <span className="text-xs text-muted-foreground">{s.task}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Log */}
        <div className="rounded-xl border border-border bg-card overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border px-4 py-3">
            <Terminal className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold text-foreground">진행 로그</h2>
          </div>
          <div className="max-h-[200px] overflow-y-auto">
            {LOGS.map((log, i) => (
              <div
                key={i}
                className="flex items-start gap-2.5 border-b border-border/30 px-4 py-2 last:border-b-0"
              >
                <span
                  className="shrink-0 text-[11px] font-medium text-primary/80"
                  style={{ fontFamily: "var(--font-geist-mono)" }}
                >
                  {log.t}
                </span>
                <span className="text-[11px] text-muted-foreground">{log.msg}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
