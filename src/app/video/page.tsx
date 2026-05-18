"use client"

import { useState, useRef, useEffect } from "react"
import {
  ChevronDown,
  Play,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Clock,
  Plus,
  Minus,
  Wand2,
  ClipboardCheck,
} from "lucide-react"

// ── Mock data ─────────────────────────────────────────────────────

const SETTINGS_OPTIONS = {
  duration: { label: "영상 길이", value: "2분 (12씬)", options: ["1분 (6씬)", "2분 (12씬)", "4분 (24씬)"] },
  scenario: { label: "시나리오", value: "B 하이브리드", options: ["A 풀 Seedance", "B 하이브리드"] },
  character: { label: "캐릭터", value: "지수", options: ["지수", "하은", "준혁"] },
  mode: { label: "모드", value: "수동", options: ["수동", "KIE 자동"] },
}

type SettingKey = keyof typeof SETTINGS_OPTIONS

const MAP_PINS = [
  { id: "wat_arun",     label: "왓아룬",    x: 22, y: 62, type: "start" as const },
  { id: "grand_palace", label: "왕궁",      x: 38, y: 28, type: "waypoint" as const },
  { id: "khao_san",     label: "카오산로드", x: 58, y: 44, type: "waypoint" as const },
  { id: "asiatique",    label: "아시아티크", x: 76, y: 72, type: "end" as const },
]

const SCENES = [
  { id: "S01", name: "왓아룬 입구 도착",  sec: 10, status: "done"    as const },
  { id: "S02", name: "계단 올라가며",      sec: 10, status: "done"    as const },
  { id: "S03", name: "전망대 도착",        sec: 10, status: "done"    as const },
  { id: "S04", name: "왕궁 이동",          sec: 10, status: "running" as const, progress: 75 },
  { id: "S05", name: "왕궁 입구",          sec: 10, status: "waiting" as const },
  { id: "S06", name: "가이드 설명",        sec: 10, status: "waiting" as const },
  { id: "S07", name: "카오산로드 진입",    sec: 10, status: "waiting" as const },
  { id: "S08", name: "야시장 둘러보기",    sec: 10, status: "waiting" as const },
  { id: "S09", name: "길거리 음식 체험",   sec: 10, status: "waiting" as const },
  { id: "S10", name: "아시아티크 도착",    sec: 10, status: "waiting" as const },
  { id: "S11", name: "대관람차 배경",      sec: 10, status: "waiting" as const },
  { id: "S12", name: "아웃트로 마무리",    sec: 10, status: "waiting" as const },
]

const PIN_COLORS = { start: "#22c55e", waypoint: "#eab308", end: "#ef4444" }
const SCENARIO_LABELS = { A: "A 풀 Seedance", B: "B 하이브리드" }

// ── Sub-components ────────────────────────────────────────────────

function SettingChip({
  settingKey,
  setting,
  onSelect,
}: {
  settingKey: SettingKey
  setting: { label: string; value: string; options: string[] }
  onSelect: (key: SettingKey, val: string) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((p) => !p)}
        className="flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-xs transition-all hover:border-primary/40"
      >
        <span className="text-muted-foreground">{setting.label}:</span>
        <span className="font-medium text-foreground">{setting.value}</span>
        <ChevronDown className={`h-3 w-3 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute left-0 top-full z-20 mt-1 min-w-[140px] rounded-lg border border-border bg-card shadow-lg">
          {setting.options.map((opt) => (
            <button
              key={opt}
              onClick={() => { onSelect(settingKey, opt); setOpen(false) }}
              className={`block w-full px-3 py-2 text-left text-xs transition-colors hover:bg-secondary/60 ${
                opt === setting.value ? "text-primary font-medium" : "text-foreground"
              }`}
            >
              {opt}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function MapPlaceholder({ pins }: { pins: typeof MAP_PINS }) {
  // Build SVG path through pin positions (percent-based)
  const points = pins.map((p) => `${p.x},${p.y}`).join(" ")

  return (
    <div className="relative h-full w-full overflow-hidden rounded-xl bg-[#141418]">
      {/* Grid lines */}
      <svg className="absolute inset-0 h-full w-full opacity-10" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#6366f1" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />
      </svg>

      {/* Route polyline (dashed) — using SVG with viewBox=0..100 */}
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <polyline
          points={points}
          fill="none"
          stroke="#8b5cf6"
          strokeWidth="0.6"
          strokeDasharray="2,1.5"
          opacity="0.7"
        />
      </svg>

      {/* Pins */}
      {pins.map((pin) => (
        <div
          key={pin.id}
          className="absolute flex -translate-x-1/2 -translate-y-full flex-col items-center"
          style={{ left: `${pin.x}%`, top: `${pin.y}%` }}
        >
          {/* Pin circle */}
          <div
            className="flex h-5 w-5 items-center justify-center rounded-full border-2 border-background shadow-md"
            style={{ backgroundColor: PIN_COLORS[pin.type] }}
          />
          {/* Label */}
          <div
            className="mt-0.5 rounded px-1.5 py-0.5 text-[10px] font-medium text-white shadow"
            style={{ backgroundColor: PIN_COLORS[pin.type] + "cc" }}
          >
            {pin.label}
          </div>
        </div>
      ))}

      {/* Zoom controls */}
      <div className="absolute right-3 top-3 flex flex-col gap-1">
        {[Plus, Minus].map((Icon, i) => (
          <button
            key={i}
            className="flex h-7 w-7 items-center justify-center rounded-lg border border-border bg-card/80 text-muted-foreground backdrop-blur-sm transition-colors hover:text-foreground"
          >
            <Icon className="h-3.5 w-3.5" />
          </button>
        ))}
      </div>

      {/* Legend */}
      <div className="absolute bottom-3 left-3 flex gap-3 rounded-lg border border-border bg-card/80 px-3 py-2 text-[10px] backdrop-blur-sm">
        {[{ color: PIN_COLORS.start, label: "출발" }, { color: PIN_COLORS.waypoint, label: "경유" }, { color: PIN_COLORS.end, label: "도착" }].map((item) => (
          <div key={item.label} className="flex items-center gap-1">
            <div className="h-2 w-2 rounded-full" style={{ backgroundColor: item.color }} />
            <span className="text-muted-foreground">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function SceneBadge({ status }: { status: "done" | "running" | "waiting" }) {
  if (status === "done")
    return (
      <span className="flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
        <CheckCircle2 className="h-2.5 w-2.5" /> 완료
      </span>
    )
  if (status === "running")
    return (
      <span className="flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-400">
        <Loader2 className="h-2.5 w-2.5 animate-spin" /> 생성 중
      </span>
    )
  return (
    <span className="flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
      <Clock className="h-2.5 w-2.5" /> 대기
    </span>
  )
}

// ── Page ──────────────────────────────────────────────────────────

export default function VideoPage() {
  const [settings, setSettings] = useState(
    Object.fromEntries(
      Object.entries(SETTINGS_OPTIONS).map(([k, v]) => [k, { ...v }])
    ) as typeof SETTINGS_OPTIONS
  )
  const [scenario, setScenario] = useState<"A" | "B">("B")

  const doneCnt = SCENES.filter((s) => s.status === "done").length
  const totalCnt = SCENES.length
  const pct = Math.round((doneCnt / totalCnt) * 100)

  function handleSettingChange(key: SettingKey, val: string) {
    setSettings((prev) => ({ ...prev, [key]: { ...prev[key], value: val } }))
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* ── Header ── */}
      <div className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold text-foreground">영상 제작</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Street View 동선을 확인하고 영상을 자동 생성합니다
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5">
          <div className="h-2 w-2 rounded-full bg-emerald-400" />
          <span className="text-xs font-medium text-foreground">방콕 여행 채널</span>
        </div>
      </div>

      {/* ── Settings chips ── */}
      <div className="flex shrink-0 items-center gap-2 border-b border-border px-6 py-3">
        <span className="mr-1 text-xs text-muted-foreground">현재 설정</span>
        {(Object.entries(settings) as [SettingKey, typeof settings[SettingKey]][]).map(([key, val]) => (
          <SettingChip key={key} settingKey={key} setting={val} onSelect={handleSettingChange} />
        ))}
      </div>

      {/* ── Main 2-col grid ── */}
      <div className="grid min-h-0 flex-1 grid-cols-5 gap-4 p-6">
        {/* Left: Map (col-span-3 = 60%) */}
        <div className="col-span-3 flex flex-col gap-3 overflow-hidden">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-foreground">여행 동선</h2>
          </div>

          {/* Map */}
          <div className="flex-1 overflow-hidden">
            <MapPlaceholder pins={MAP_PINS} />
          </div>

          {/* Map action buttons */}
          <div className="flex gap-2">
            <button className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-border py-2.5 text-sm font-medium text-foreground transition-all hover:bg-secondary/40">
              <ClipboardCheck className="h-4 w-4 text-muted-foreground" />
              직접 검수
            </button>
            <button className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-primary py-2.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90">
              <Wand2 className="h-4 w-4" />
              ✦ 자동 동선
            </button>
          </div>
        </div>

        {/* Right: Scene list (col-span-2 = 40%) */}
        <div className="col-span-2 flex flex-col overflow-hidden rounded-xl border border-border bg-card">
          {/* Scene list header */}
          <div className="shrink-0 border-b border-border px-4 py-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-foreground">씬 목록</h2>
              <span
                className="text-sm font-bold text-foreground"
                style={{ fontFamily: "var(--font-geist-mono)" }}
              >
                {doneCnt} / {totalCnt}
              </span>
            </div>
            {/* Progress bar */}
            <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-secondary">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>
            <p className="mt-1 text-right text-[10px] text-muted-foreground">{pct}% 완료</p>
          </div>

          {/* Scene items — scrollable */}
          <div className="flex-1 overflow-y-auto">
            {SCENES.map((scene) => (
              <div
                key={scene.id}
                className={`flex items-center gap-3 border-b border-border/50 px-4 py-2.5 transition-colors last:border-b-0 ${
                  scene.status === "running" ? "bg-amber-500/5" : ""
                }`}
              >
                {/* Scene ID */}
                <span
                  className="w-8 shrink-0 text-xs font-bold text-muted-foreground"
                  style={{ fontFamily: "var(--font-geist-mono)" }}
                >
                  {scene.id}
                </span>

                {/* Name + progress */}
                <div className="flex-1 min-w-0">
                  <p className="truncate text-xs font-medium text-foreground">{scene.name}</p>
                  {scene.status === "running" && "progress" in scene && (
                    <div className="mt-1 h-1 overflow-hidden rounded-full bg-secondary">
                      <div
                        className="h-full rounded-full bg-amber-400 transition-all"
                        style={{ width: `${scene.progress}%` }}
                      />
                    </div>
                  )}
                </div>

                {/* Duration */}
                <span className="shrink-0 text-[10px] text-muted-foreground/60">
                  {scene.sec}초
                </span>

                {/* Badge */}
                <SceneBadge status={scene.status} />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Scenario toggle ── */}
      <div className="shrink-0 border-t border-border px-6 py-3">
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">시나리오 전환</span>
          <div className="flex rounded-lg border border-border bg-card p-0.5">
            {(["A", "B"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setScenario(s)}
                className={`rounded-md px-4 py-1.5 text-xs font-medium transition-all ${
                  scenario === s
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {SCENARIO_LABELS[s]}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Action bar ── */}
      <div className="shrink-0 flex items-center justify-between border-t border-border bg-card/50 px-6 py-4">
        <div className="flex items-center gap-2 text-xs text-amber-400/80">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          <span>시나리오를 변경하면 모든 씬이 재생성됩니다</span>
        </div>
        <button className="flex items-center gap-2 rounded-lg bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground shadow-lg shadow-primary/20 transition-opacity hover:opacity-90">
          <Play className="h-4 w-4 fill-current" />
          영상 생성 시작
        </button>
      </div>
    </div>
  )
}
