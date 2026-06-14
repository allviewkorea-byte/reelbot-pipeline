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
  youtube_url?: string | null // 업로드 성공 시 결과 URL(플랫폼 노드 점등·클릭용)
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

// 상태 → currentColor 토큰(기존 토큰만). 발광/채움은 이 currentColor 를 파생해 쓴다.
const TEXT: Record<NodeState, string> = {
  done: "text-emerald-500",
  active: "text-primary",
  pending: "text-muted-foreground",
  error: "text-red-500",
}

// ── 지오메트리(둥근 사각형 노드 1행) ────────────────────────────────
const NODE_W = 66
const NODE_H = 30
const CY = 36
const START_X = 45
const GAP = 105
const cx = (i: number) => START_X + i * GAP
const LAST_X = cx(NODES.length - 1)
const PX = LAST_X + 95 // 플랫폼 분기 x
const PLATFORM_Y = [6, 26, 46, 66]

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
  const uploadDone = states[states.length - 1] === "done"
  const youtubeUrl = job?.youtube_url ?? null
  // 실데이터(youtube_url) 우선, 없으면 '업로드 노드 done ⇒ 유튜브 done' 근사(백곰=유튜브 단일).
  const youtubeDone = Boolean(youtubeUrl) || uploadDone
  const progress = job && job.status === "running" ? job.progress : null

  // 테크 스타일 고정(차분한 회로/전류). 발광은 active 노드만 은은하게.
  const glowFor = (st: NodeState) => (st === "active" ? "glow-soft" : "")

  return (
    <div className="rounded-xl border border-border bg-card p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-foreground">백곰 파이프라인</h2>
        <span className="text-xs text-muted-foreground">{headerText(job)}</span>
      </div>

      <div className="w-full overflow-x-auto">
        <svg viewBox={`0 0 ${PX + 75} 72`} className="h-auto w-full min-w-[680px]" role="img" aria-label="파이프라인 상태">
          {/* 노드 간 연결선 — done→done(emerald)·done→active(primary) 구간에 전류 흐름 */}
          {NODES.slice(0, -1).map((_, i) => {
            const a = states[i]
            const b = states[i + 1]
            const flowing = a === "done" && (b === "done" || b === "active")
            const cls = !flowing
              ? "stroke-border"
              : `flow-line stroke-current ${b === "active" ? "text-primary" : "text-emerald-500"}`
            return (
              <line
                key={`c-${i}`}
                x1={cx(i) + NODE_W / 2}
                y1={CY}
                x2={cx(i + 1) - NODE_W / 2}
                y2={CY}
                className={cls}
                strokeWidth={flowing ? 1.8 : 1.5}
              />
            )
          })}

          {/* 끝(업로드) → 플랫폼 분기선 — 실제 업로드된 유튜브(i=0)만 전류 흐름 */}
          {PLATFORM_Y.map((py, i) => {
            const lit = i === 0 && youtubeDone
            return (
              <line
                key={`pl-${i}`}
                x1={LAST_X + NODE_W / 2}
                y1={CY}
                x2={PX - 7}
                y2={py}
                className={lit ? "flow-line stroke-current text-emerald-500" : "stroke-border"}
                strokeWidth={1.4}
              />
            )
          })}

          {/* 플랫폼 노드 — 유튜브(i=0)만 업로드 시 점등(+✓, youtube_url 있으면 클릭 이동) */}
          {PLATFORM_Y.map((py, i) => {
            const lit = i === 0 && youtubeDone
            const inner = (
              <g className={`${lit ? "text-emerald-500" : "text-muted-foreground"} ${i === 0 && youtubeUrl ? "cursor-pointer" : ""}`}>
                <circle
                  cx={PX}
                  cy={py}
                  r={6}
                  className={`fill-current ${lit ? "glow-soft" : ""}`}
                  fillOpacity={lit ? 1 : 0.35}
                  stroke="currentColor"
                  strokeWidth={1.2}
                />
                {lit && (
                  <text x={PX} y={py + 3} textAnchor="middle" fontSize={8} className="fill-white">
                    ✓
                  </text>
                )}
                <text x={PX + 12} y={py + 3} className="fill-current" fontSize={9}>
                  {PLATFORMS[i]}
                </text>
              </g>
            )
            return i === 0 && youtubeUrl ? (
              <a key={`pn-${i}`} href={youtubeUrl} target="_blank" rel="noreferrer">
                {inner}
              </a>
            ) : (
              <g key={`pn-${i}`}>{inner}</g>
            )
          })}

          {/* 메인 노드 — 둥근 사각형 카드(차분한 테크) */}
          {NODES.map((n, i) => {
            const st = states[i]
            const x = cx(i) - NODE_W / 2
            const y = CY - NODE_H / 2
            return (
              <g key={n.id} className={TEXT[st]}>
                {st === "active" && (
                  <rect
                    x={x - 4}
                    y={y - 4}
                    width={NODE_W + 8}
                    height={NODE_H + 8}
                    rx={10}
                    className="fill-current pulse-tech"
                  />
                )}
                <rect
                  x={x}
                  y={y}
                  width={NODE_W}
                  height={NODE_H}
                  rx={8}
                  className={`fill-current ${glowFor(st)}`}
                  fillOpacity={st === "pending" ? 0.06 : 0.1}
                  stroke="currentColor"
                  strokeWidth={1.4}
                />
                <text
                  x={cx(i)}
                  y={CY + 3.5}
                  textAnchor="middle"
                  fontSize={10}
                  className={st === "pending" ? "fill-muted-foreground" : "fill-current"}
                >
                  {n.label}
                </text>
                {st === "done" && (
                  <text x={x + NODE_W - 9} y={y + 11} textAnchor="middle" fontSize={9} className="fill-current">
                    ✓
                  </text>
                )}
                {st === "error" && (
                  <text x={x + NODE_W - 9} y={y + 11} textAnchor="middle" fontSize={9} className="fill-current">
                    !
                  </text>
                )}
                {st === "active" && progress !== null && (
                  <text x={cx(i)} y={CY + NODE_H / 2 + 12} textAnchor="middle" fontSize={9} className="fill-current">
                    {progress}%
                  </text>
                )}
              </g>
            )
          })}

          <style jsx>{`
            /* 전류 흐름 — 점선 입자가 왼→오로 은은하게 흐른다(테크) */
            .flow-line {
              stroke-dasharray: 4 6;
              animation: flowDash 1.6s linear infinite;
            }
            @keyframes flowDash {
              to {
                stroke-dashoffset: -10;
              }
            }
            /* 발광 — currentColor(토큰 색)에서 파생. 테크=은은 */
            .glow-soft {
              filter: drop-shadow(0 0 2px currentColor);
            }
            /* active 노드 맥동 링 */
            .pulse-tech {
              fill-opacity: 0.18;
              animation: pulseTech 1.8s ease-in-out infinite;
            }
            @keyframes pulseTech {
              0%,
              100% {
                fill-opacity: 0.16;
              }
              50% {
                fill-opacity: 0.04;
              }
            }
            @media (prefers-reduced-motion: reduce) {
              .flow-line,
              .pulse-tech {
                animation: none;
              }
            }
          `}</style>
        </svg>
      </div>
    </div>
  )
}
