"use client"

import { useState } from "react"
import { CheckCircle2, Layers, Wand2, Send } from "lucide-react"

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

const APPS = [
  {
    id: "premiere",
    name: "Adobe Premiere Pro",
    detail: "버전 25.4 · 연결됨",
    color: "#9999ff",
    bg: "bg-[#9999ff]/10",
    letter: "Pr",
  },
  {
    id: "ae",
    name: "Adobe After Effects",
    detail: "모션그래픽 연동",
    color: "#9999ff",
    bg: "bg-[#9999ff]/10",
    letter: "Ae",
  },
]

const EDIT_OPTS_INIT = [
  { id: "color", label: "색보정 자동 적용", on: true },
  { id: "subtitle", label: "자막 스타일 자동 적용", on: true },
  { id: "transition", label: "트랜지션 자동 삽입", on: true },
  { id: "autoupload", label: "편집 후 자동 업로드", on: false },
]

const FIREFLY_OPTS_INIT = [
  { id: "motion", label: "모션 트래킹", on: true },
  { id: "grade", label: "자동 컬러 그레이딩", on: true },
  { id: "noise", label: "노이즈 제거", on: false },
]

export default function AdobePage() {
  const [editOpts, setEditOpts] = useState(EDIT_OPTS_INIT)
  const [fireflyOpts, setFireflyOpts] = useState(FIREFLY_OPTS_INIT)

  const toggle = (
    setter: React.Dispatch<React.SetStateAction<typeof EDIT_OPTS_INIT>>,
    id: string
  ) => setter((prev) => prev.map((o) => (o.id === id ? { ...o, on: !o.on } : o)))

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-auto p-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">Adobe Premiere 연동</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          세부 편집이 필요할 때 프리미어로 연결됩니다
        </p>
      </div>

      {/* Connected apps */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="mb-4 flex items-center gap-2">
          <Layers className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold text-foreground">연결된 Adobe 앱</h2>
        </div>
        <div className="flex flex-col gap-3">
          {APPS.map((app) => (
            <div key={app.id} className="flex items-center gap-3 rounded-lg bg-secondary/30 p-3">
              <div
                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${app.bg} border border-[#9999ff]/20`}
              >
                <span className="text-xs font-bold" style={{ color: app.color }}>
                  {app.letter}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-foreground">{app.name}</p>
                <p className="text-xs text-muted-foreground">{app.detail}</p>
              </div>
              <span className="flex items-center gap-1 rounded-full bg-emerald-500/15 px-2.5 py-1 text-xs font-medium text-emerald-400">
                <CheckCircle2 className="h-3 w-3" /> 연결됨
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Edit options */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h2 className="mb-4 text-sm font-semibold text-foreground">자동 편집 옵션</h2>
        <div className="flex flex-col gap-3">
          {editOpts.map((o) => (
            <div key={o.id} className="flex items-center justify-between">
              <span className="text-sm text-foreground">{o.label}</span>
              <Toggle on={o.on} onChange={() => toggle(setEditOpts, o.id)} />
            </div>
          ))}
        </div>
      </div>

      {/* Firefly */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="mb-4 flex items-center gap-2">
          <Wand2 className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold text-foreground">Adobe Firefly AI 효과</h2>
        </div>
        <div className="flex flex-col gap-3">
          {fireflyOpts.map((o) => (
            <div key={o.id} className="flex items-center justify-between">
              <span className="text-sm text-foreground">{o.label}</span>
              <Toggle on={o.on} onChange={() => toggle(setFireflyOpts, o.id)} />
            </div>
          ))}
        </div>
      </div>

      {/* Action */}
      <button className="flex items-center justify-center gap-2 rounded-xl bg-primary py-3 text-sm font-semibold text-primary-foreground shadow-lg shadow-primary/20 transition-opacity hover:opacity-90">
        <Send className="h-4 w-4" />
        프리미어로 영상 전송하기
      </button>
    </div>
  )
}
