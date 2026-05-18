"use client"

import { useState } from "react"
import {
  PlayCircle,
  Music2,
  Share2,
  Plus,
  Clock,
  CheckCircle2,
  ChevronRight,
  CalendarDays,
} from "lucide-react"

// ── Toggle component ──────────────────────────────────────────────
function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!on)}
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none ${
        on ? "bg-primary" : "bg-secondary"
      }`}
    >
      <span
        className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-lg transition-transform duration-200 ${
          on ? "translate-x-4" : "translate-x-0"
        }`}
      />
    </button>
  )
}

// ── Mock data ─────────────────────────────────────────────────────
const PLATFORMS_INIT = [
  {
    id: "youtube",
    name: "유튜브",
    detail: "3개 채널",
    connected: true,
    on: true,
    icon: PlayCircle,
    color: "#ef4444",
    bg: "bg-red-500/10",
  },
  {
    id: "tiktok",
    name: "틱톡",
    detail: "1개 계정",
    connected: true,
    on: true,
    icon: Music2,
    color: "#3b82f6",
    bg: "bg-blue-500/10",
  },
  {
    id: "instagram",
    name: "인스타그램",
    detail: "릴스",
    connected: true,
    on: true,
    icon: Share2,
    color: "#f97316",
    bg: "bg-orange-500/10",
  },
]

const SCHEDULE_INIT = [
  { id: "daily9", label: "매일 오전 9시 자동 업로드", on: true },
  { id: "3perday", label: "하루 3편 자동 발행", on: true },
  { id: "comment", label: "댓글 AI 자동 답변", on: false },
  { id: "trend", label: "트렌드 자동 감지 후 업로드", on: true },
]

const DAYS = ["월", "화", "수", "목", "금", "토", "일"]
const DAYS_INIT = ["월", "화", "수", "목", "금"]

const HISTORY = [
  { title: "방콕 왓아룬 브이로그", channel: "방콕 채널", platform: "유튜브", platformColor: "#ef4444", time: "2시간 전", ok: true },
  { title: "도쿄 시부야 거리", channel: "도쿄 채널", platform: "틱톡", platformColor: "#3b82f6", time: "5시간 전", ok: true },
  { title: "파리 에펠탑 야경", channel: "유럽 채널", platform: "인스타그램", platformColor: "#f97316", time: "1일 전", ok: true },
  { title: "카오산로드 야시장", channel: "방콕 채널", platform: "유튜브", platformColor: "#ef4444", time: "2일 전", ok: true },
  { title: "도쿄 라멘 먹방", channel: "도쿄 채널", platform: "틱톡", platformColor: "#3b82f6", time: "3일 전", ok: true },
]

// ── Page ──────────────────────────────────────────────────────────
export default function UploadPage() {
  const [platforms, setPlatforms] = useState(PLATFORMS_INIT)
  const [schedule, setSchedule] = useState(SCHEDULE_INIT)
  const [activeDays, setActiveDays] = useState<string[]>(DAYS_INIT)

  function togglePlatform(id: string) {
    setPlatforms((p) => p.map((pl) => pl.id === id ? { ...pl, on: !pl.on } : pl))
  }
  function toggleSchedule(id: string) {
    setSchedule((s) => s.map((sc) => sc.id === id ? { ...sc, on: !sc.on } : sc))
  }
  function toggleDay(day: string) {
    setActiveDays((d) => d.includes(day) ? d.filter((x) => x !== day) : [...d, day])
  }

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-auto p-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-foreground">멀티 플랫폼 업로드</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          한 번에 여러 플랫폼에 자동 업로드됩니다
        </p>
      </div>

      {/* Platform grid */}
      <div>
        <h2 className="mb-3 text-sm font-semibold text-foreground">연결된 플랫폼</h2>
        <div className="grid grid-cols-2 gap-3">
          {platforms.map((pl) => (
            <div
              key={pl.id}
              className="flex items-center gap-3 rounded-xl border border-border bg-card p-4 transition-colors hover:border-border/80"
            >
              {/* Icon */}
              <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${pl.bg}`}>
                <pl.icon className="h-5 w-5" style={{ color: pl.color }} />
              </div>
              {/* Info */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-foreground">{pl.name}</p>
                <div className="mt-0.5 flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  <span className="text-xs text-muted-foreground">연결됨 · {pl.detail}</span>
                </div>
              </div>
              <Toggle on={pl.on} onChange={() => togglePlatform(pl.id)} />
            </div>
          ))}

          {/* Add platform */}
          <button className="flex items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-transparent p-4 text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground">
            <Plus className="h-4 w-4" />
            플랫폼 추가
            <span className="ml-1 text-xs opacity-60">네이버TV · 카카오TV</span>
          </button>
        </div>
      </div>

      {/* Schedule card */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="mb-4 flex items-center gap-2">
          <CalendarDays className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold text-foreground">업로드 스케줄</h2>
        </div>

        <div className="flex flex-col gap-3">
          {schedule.map((sc) => (
            <div key={sc.id} className="flex items-center justify-between">
              <span className="text-sm text-foreground">{sc.label}</span>
              <Toggle on={sc.on} onChange={() => toggleSchedule(sc.id)} />
            </div>
          ))}
        </div>

        {/* Day selector */}
        <div className="mt-4 border-t border-border pt-4">
          <p className="mb-2.5 text-xs text-muted-foreground">업로드 요일</p>
          <div className="flex gap-1.5">
            {DAYS.map((day) => {
              const active = activeDays.includes(day)
              return (
                <button
                  key={day}
                  onClick={() => toggleDay(day)}
                  className={`flex h-8 w-8 items-center justify-center rounded-lg text-xs font-medium transition-all ${
                    active
                      ? "bg-primary text-primary-foreground"
                      : "bg-secondary text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {day}
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* Upload history */}
      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-foreground">업로드 이력</h2>
          <button className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            전체 보기 <ChevronRight className="h-3 w-3" />
          </button>
        </div>
        <div>
          {HISTORY.map((item, i) => (
            <div
              key={i}
              className="flex items-center gap-3 border-b border-border/50 px-4 py-3 last:border-b-0 hover:bg-secondary/20 transition-colors"
            >
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
              <div className="flex-1 min-w-0">
                <p className="truncate text-xs font-medium text-foreground">{item.title}</p>
                <p className="text-[11px] text-muted-foreground">{item.channel}</p>
              </div>
              <span
                className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium"
                style={{ backgroundColor: item.platformColor + "20", color: item.platformColor }}
              >
                {item.platform}
              </span>
              <div className="flex shrink-0 items-center gap-1 text-[11px] text-muted-foreground">
                <Clock className="h-3 w-3" />
                {item.time}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
