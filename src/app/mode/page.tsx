"use client"

import { useState } from "react"
import { Bot, Camera } from "lucide-react"

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!on)}
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ${
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

const MODES = [
  {
    id: "auto",
    label: "자동화",
    desc: "GPT-4o + Seedance + 자동 대본 + 자동 업로드",
    icon: Bot,
  },
  {
    id: "normal",
    label: "반자동",
    desc: "직접 촬영 영상 + 자동 편집만",
    icon: Camera,
  },
]

const FEATURES_INIT = [
  { id: "character", label: "AI 캐릭터 사용", on: true },
  { id: "seedance", label: "Seedance 영상 생성", on: true },
  { id: "competitor", label: "경쟁사 자동 분석", on: true },
  { id: "monetize", label: "수익화 분석", on: true },
  { id: "trend", label: "트렌드 자동 감지", on: true },
  { id: "comment", label: "댓글 AI 답변", on: false },
]

const CHANNEL_MODES = [
  { channel: "방콕 여행", mode: "자동화", modeId: "auto" },
  { channel: "도쿄 일상", mode: "반자동", modeId: "normal" },
  { channel: "유럽 감성", mode: "반자동", modeId: "normal" },
]

const MODE_BADGE: Record<string, string> = {
  auto: "bg-primary/15 text-primary",
  normal: "bg-secondary text-muted-foreground",
}

export default function ModePage() {
  const [selectedMode, setSelectedMode] = useState("auto")
  const [features, setFeatures] = useState(FEATURES_INIT)

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-auto p-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">모드 설정</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">자동화와 반자동 중 선택하세요</p>
      </div>

      {/* Mode selector */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h2 className="mb-4 text-sm font-semibold text-foreground">운영 모드</h2>
        <div className="flex flex-col gap-2">
          {MODES.map((m) => {
            const active = selectedMode === m.id
            return (
              <button
                key={m.id}
                onClick={() => setSelectedMode(m.id)}
                className={`flex items-center gap-3 rounded-lg border p-3.5 text-left transition-all ${
                  active
                    ? "border-primary/40 bg-primary/5"
                    : "border-border bg-transparent hover:bg-secondary/30"
                }`}
              >
                {/* Radio dot */}
                <div
                  className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 transition-colors ${
                    active ? "border-primary" : "border-muted-foreground/40"
                  }`}
                >
                  {active && <div className="h-2 w-2 rounded-full bg-primary" />}
                </div>

                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-semibold ${active ? "text-foreground" : "text-muted-foreground"}`}>
                    {m.label}
                  </p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{m.desc}</p>
                </div>

                {active && (
                  <span className="shrink-0 rounded-full bg-primary/15 px-2.5 py-1 text-xs font-medium text-primary">
                    선택됨
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {/* Feature toggles */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h2 className="mb-4 text-sm font-semibold text-foreground">기능 토글</h2>
        <div className="flex flex-col gap-3">
          {features.map((f) => (
            <div key={f.id} className="flex items-center justify-between">
              <span className="text-sm text-foreground">{f.label}</span>
              <Toggle
                on={f.on}
                onChange={() =>
                  setFeatures((prev) =>
                    prev.map((x) => (x.id === f.id ? { ...x, on: !x.on } : x))
                  )
                }
              />
            </div>
          ))}
        </div>
      </div>

      {/* Channel mode table */}
      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-foreground">채널별 모드</h2>
        </div>
        <table className="w-full">
          <thead>
            <tr className="border-b border-border/50">
              <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">채널</th>
              <th className="px-4 py-2.5 text-left text-xs font-medium text-muted-foreground">모드</th>
            </tr>
          </thead>
          <tbody>
            {CHANNEL_MODES.map((row, i) => (
              <tr key={i} className="border-b border-border/30 last:border-b-0 hover:bg-secondary/20 transition-colors">
                <td className="px-4 py-3 text-sm text-foreground">{row.channel}</td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${MODE_BADGE[row.modeId]}`}>
                    {row.mode}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
