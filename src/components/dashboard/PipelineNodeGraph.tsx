"use client"

import { useEffect, useState } from "react"

// 백곰 파이프라인 노드 ↔ orchestrate 진행률(%) 밴드 매핑(실측).
// BGM·자막·사연자동생성은 별도 진행률이 없어 합쳐서 표현(세분화는 UI-4b).
type NodeState = "done" | "active" | "pending" | "error"

interface PipelineNode {
  id: string
  label: string
  to: number // 이 진행률(%)을 넘기면 done 으로 간주
}

const NODES: PipelineNode[] = [
  { id: "script", label: "사연", to: 10 },
  { id: "director", label: "디렉터", to: 12 },
  { id: "storyboard", label: "콘티", to: 25 },
  { id: "video", label: "영상", to: 55 },
  { id: "audio", label: "TTS·BGM", to: 70 },
  { id: "assemble", label: "합성", to: 98 },
  { id: "upload", label: "업로드", to: 100 },
]

const PLATFORMS = ["유튜브", "틱톡", "인스타", "클립"]

interface ActiveJob {
  job_id: string
  status: string // pending | running | completed | failed
  progress: number
  current_step: string
}

function computeStates(job: ActiveJob | null): NodeState[] {
  if (!job) return NODES.map(() => "pending")
  if (job.status === "completed") return NODES.map(() => "done")
  const p = job.progress
  let activeIdx = NODES.findIndex((n) => p < n.to)
  if (activeIdx === -1) activeIdx = NODES.length - 1
  return NODES.map((_, i) => {
    if (i < activeIdx) return "done"
    if (i === activeIdx) return job.status === "failed" ? "error" : "active"
    return "pending"
  })
}

// 노드 채움색 — 기존 디자인 토큰만(새 색 금지).
const FILL: Record<NodeState, string> = {
  done: "fill-emerald-500",
  active: "fill-primary",
  pending: "fill-secondary",
  error: "fill-red-500",
}

const NODE_R = 15
const CY = 55
const START_X = 40
const GAP = 105
const cx = (i: number) => START_X + i * GAP
const LAST_X = cx(NODES.length - 1)
const PX = LAST_X + 100 // 플랫폼 분기 x
const PLATFORM_Y = [18, 42, 66, 90]

function headerText(job: ActiveJob | null): string {
  if (!job) return "대기 중 — 진행 중인 작업 없음"
  if (job.status === "completed") return "최근 완료 · 100%"
  if (job.status === "failed") return `실패: ${job.current_step || "오류"}`
  return `${job.current_step || "진행 중"} · ${job.progress}%`
}

export function PipelineNodeGraph() {
  const [job, setJob] = useState<ActiveJob | null>(null)

  useEffect(() => {
    let active = true
    const load = () => {
      fetch("/api/jobs/active")
        .then((r) => r.json())
        .then((d) => {
          if (!active) return
          setJob(d && typeof d.job_id === "string" ? (d as ActiveJob) : null)
        })
        .catch(() => {
          if (active) setJob(null)
        })
    }
    load()
    const timer = setInterval(load, 5000)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [])

  const states = computeStates(job)

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-foreground">백곰 파이프라인</h2>
        <span className="text-xs text-muted-foreground">{headerText(job)}</span>
      </div>

      <div className="w-full overflow-x-auto">
        <svg viewBox={`0 0 ${PX + 70} 120`} className="h-auto w-full min-w-[640px]" role="img" aria-label="파이프라인 상태">
          {/* 노드 간 연결선 */}
          {NODES.slice(0, -1).map((_, i) => (
            <line
              key={`c-${i}`}
              x1={cx(i) + NODE_R}
              y1={CY}
              x2={cx(i + 1) - NODE_R}
              y2={CY}
              className="stroke-border"
              strokeWidth={2}
            />
          ))}

          {/* 끝(업로드) → 플랫폼 분기선 + 노드 */}
          {PLATFORM_Y.map((py, i) => (
            <line
              key={`pl-${i}`}
              x1={LAST_X + NODE_R}
              y1={CY}
              x2={PX - 6}
              y2={py}
              className="stroke-border"
              strokeWidth={1.5}
            />
          ))}
          {PLATFORM_Y.map((py, i) => (
            <g key={`pn-${i}`}>
              <circle cx={PX} cy={py} r={5} className="fill-secondary" />
              <text x={PX + 10} y={py + 3} className="fill-muted-foreground" fontSize={9}>
                {PLATFORMS[i]}
              </text>
            </g>
          ))}

          {/* 메인 노드 */}
          {NODES.map((n, i) => {
            const st = states[i]
            return (
              <g key={n.id}>
                {st === "active" && (
                  <circle cx={cx(i)} cy={CY} r={NODE_R + 7} className="pulse-ring fill-primary" />
                )}
                <circle cx={cx(i)} cy={CY} r={NODE_R} className={FILL[st]} />
                {st === "done" && (
                  <text x={cx(i)} y={CY + 4} textAnchor="middle" fontSize={13} className="fill-white">
                    ✓
                  </text>
                )}
                {st === "error" && (
                  <text x={cx(i)} y={CY + 4} textAnchor="middle" fontSize={13} className="fill-white">
                    !
                  </text>
                )}
                <text
                  x={cx(i)}
                  y={CY + 33}
                  textAnchor="middle"
                  fontSize={11}
                  className={st === "pending" ? "fill-muted-foreground" : "fill-foreground"}
                >
                  {n.label}
                </text>
              </g>
            )
          })}

          <style jsx>{`
            .pulse-ring {
              opacity: 0.35;
              animation: nodePulse 1.5s ease-in-out infinite;
            }
            @keyframes nodePulse {
              0%,
              100% {
                opacity: 0.35;
              }
              50% {
                opacity: 0.1;
              }
            }
            @media (prefers-reduced-motion: reduce) {
              .pulse-ring {
                animation: none;
              }
            }
          `}</style>
        </svg>
      </div>
    </div>
  )
}
