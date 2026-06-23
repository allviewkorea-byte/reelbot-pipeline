// 음악 파이프라인 작업(운영 가시성, #36) — 프론트 공용 타입 + 단계 매핑.

export type MusicJobType = "manual_render" | "cron" | "rerender"
export type MusicJobStatus = "queued" | "running" | "completed" | "failed"

export interface MusicJob {
  job_id: string
  type: MusicJobType
  mix_id?: string | null
  status: MusicJobStatus
  step?: string | null
  step_progress?: number
  steps_completed?: string[]
  error_message?: string | null
  metadata?: Record<string, unknown> | null
  created_at?: string
  updated_at?: string
  completed_at?: string | null
}

// 표준 단계 → 파이프라인 노드 인덱스(노드 순서: 주제0·음원1·가사2·영상3·합성4·업로드5).
export const STEP_NODE_INDEX: Record<string, number> = {
  theme: 0,
  vocal: 1,
  lyrics: 2,
  video: 3,
  mix: 4,
  translate: 5,
  upload: 5,
}

export const JOB_TYPE_LABEL: Record<MusicJobType, string> = {
  manual_render: "수동 영상 생성",
  cron: "자동 제작",
  rerender: "재렌더",
}

export const STEP_LABEL: Record<string, string> = {
  theme: "주제 결정",
  vocal: "음원 생성",
  lyrics: "가사 생성",
  video: "영상 렌더",
  mix: "합성",
  translate: "다국어 번역",
  upload: "업로드",
}

// 상대 시각(예: "5분 전"). created_at(ISO) → 한국어.
export function relTime(iso?: string): string {
  if (!iso) return ""
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ""
  const sec = Math.max(0, Math.floor((Date.now() - t) / 1000))
  if (sec < 60) return "방금 전"
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}분 전`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}시간 전`
  return `${Math.floor(hr / 24)}일 전`
}
