"use client"

import { STEP_NODE_INDEX, type MusicJob } from "@/lib/music-jobs"

// 음악 파이프라인 노드그래프 — 백곰 PipelineNodeGraph 구조·className·SVG 지오메트리 1:1 복제
// (직접 import 금지, 시각 일치 목적). #36: activeJobs 로 실제 진행을 노드에 반영(없으면 전부 pending).
type NodeState = "done" | "active" | "pending" | "error"

interface PipelineNode {
  id: string
  label: string
}

const NODES: PipelineNode[] = [
  { id: "theme", label: "주제" },
  { id: "audio", label: "음원" },
  { id: "lyrics", label: "가사" },
  { id: "video", label: "영상" },
  { id: "assemble", label: "합성" },
  { id: "upload", label: "업로드" },
]

const PLATFORMS = ["유튜브"]

const TEXT: Record<NodeState, string> = {
  done: "text-emerald-500",
  active: "text-primary",
  pending: "text-muted-foreground",
  error: "text-red-500",
}

// ── 지오메트리(둥근 사각형 노드 1행) — 백곰과 동일 ──────────────────
const NODE_W = 66
const NODE_H = 28
const CY = 28
const START_X = 45
const GAP = 105
const cx = (i: number) => START_X + i * GAP
const LAST_X = cx(NODES.length - 1)
const PX = LAST_X + 95
const PLATFORM_Y = [28] // 음악은 유튜브 단일 → 중앙

// 진행 중(또는 미확인 실패) 작업 → 노드 상태 배열. running 우선, 없으면 queued/failed.
function deriveStates(jobs: MusicJob[]): { states: NodeState[]; errorAt: number; errorMsg?: string } {
  const states: NodeState[] = NODES.map(() => "pending")
  const job =
    jobs.find((j) => j.status === "running") ||
    jobs.find((j) => j.status === "queued") ||
    jobs.find((j) => j.status === "failed")
  if (!job) return { states, errorAt: -1 }
  const idx = STEP_NODE_INDEX[job.step ?? ""] ?? 0
  for (let i = 0; i < NODES.length; i++) {
    if (i < idx) states[i] = "done"
    else if (i === idx) states[i] = job.status === "failed" ? "error" : "active"
    else states[i] = "pending"
  }
  return {
    states,
    errorAt: job.status === "failed" ? idx : -1,
    errorMsg: job.error_message ?? undefined,
  }
}

export function MusicPipeline({ activeJobs = [] }: { activeJobs?: MusicJob[] }) {
  const { states, errorAt, errorMsg } = deriveStates(activeJobs)
  const running = activeJobs.some((j) => j.status === "running" || j.status === "queued")

  return (
    <div className="rounded-xl border border-border bg-card px-3 py-2">
      <div className="mb-1 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-foreground">음악 파이프라인</h2>
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              errorAt >= 0 ? "bg-red-500" : running ? "bg-primary animate-pulse" : "bg-muted-foreground/40"
            }`}
          />
          {errorAt >= 0 ? "실패" : running ? "진행 중" : "유휴"}
        </span>
      </div>

      <div className="w-full overflow-x-auto">
        <svg viewBox={`0 0 ${PX + 75} 56`} className="h-auto w-full min-w-[680px]" role="img" aria-label="파이프라인 상태">
          {/* 노드 간 연결선 */}
          {NODES.slice(0, -1).map((_, i) => (
            <line
              key={`c-${i}`}
              x1={cx(i) + NODE_W / 2}
              y1={CY}
              x2={cx(i + 1) - NODE_W / 2}
              y2={CY}
              className="stroke-border"
              strokeWidth={1.5}
            />
          ))}

          {/* 끝(업로드) → 유튜브 분기선 */}
          {PLATFORM_Y.map((py, i) => (
            <line
              key={`pl-${i}`}
              x1={LAST_X + NODE_W / 2}
              y1={CY}
              x2={PX - 7}
              y2={py}
              className="stroke-border"
              strokeWidth={1.4}
            />
          ))}

          {/* 유튜브 분기 노드 */}
          {PLATFORM_Y.map((py, i) => (
            <g key={`pn-${i}`} className="text-muted-foreground">
              <circle cx={PX} cy={py} r={6} className="fill-current" fillOpacity={0.35} stroke="currentColor" strokeWidth={1.2} />
              <text x={PX + 12} y={py + 3} className="fill-current" fontSize={9}>
                {PLATFORMS[i]}
              </text>
            </g>
          ))}

          {/* 메인 노드 — 둥근 사각형 카드 */}
          {NODES.map((n, i) => {
            const st = states[i]
            const x = cx(i) - NODE_W / 2
            const y = CY - NODE_H / 2
            const isActive = st === "active"
            const isError = st === "error"
            return (
              <g key={n.id} className={`${TEXT[st]} ${isActive ? "animate-pulse" : ""}`}>
                {/* 실패 노드 호버 시 네이티브 툴팁(에러 메시지) */}
                {isError && errorMsg ? <title>{errorMsg}</title> : null}
                <rect
                  x={x}
                  y={y}
                  width={NODE_W}
                  height={NODE_H}
                  rx={8}
                  className="fill-current"
                  fillOpacity={isActive || isError ? 0.16 : st === "done" ? 0.1 : 0.06}
                  stroke="currentColor"
                  strokeWidth={isActive || isError ? 1.8 : 1.4}
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
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}
