// FastAPI 백엔드 호출 클라이언트 (Phase 2)
// 백엔드 스키마: travel-pipeline/api/schemas.py 와 일치시킬 것.

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

// ── 타입 (Pydantic 모델과 1:1) ────────────────────────────────────

// 백엔드 main.generate_scenario() 가 반환하는 씬 모양과 일치.
export interface Scene {
  scene_id: number
  location?: string
  description?: string
  camera?: string
  narration?: string
  prompt_en?: string
  duration_sec?: number
}

export interface ScenarioResponse {
  country?: string
  duration_min?: number
  scenario?: string
  scenes: Scene[]
}

export interface Storyboard {
  scene_id: number | string
  image_path?: string
  image_url?: string
  prompt?: string
  [key: string]: unknown
}

export interface StoryboardGenerateParams {
  scenario?: string
  character_name?: string
  character_image_path?: string | null
  scenes: Scene[] | Record<string, unknown>[]
  storyboard_model?: string
}

export interface SceneRegenerateParams {
  job_id: string
  scene_id: number
  scene: Record<string, unknown>
  character_image_path?: string | null
  extra_instructions?: string | null
  storyboard_model?: string
}

export interface VideoStartParams {
  job_id: string
  scenes: Record<string, unknown>[]
  approved_storyboards: Storyboard[]
  scenario_mode?: string
  seedance_mode?: string
  video_model?: string
  character_id?: string | null
}

export type JobState =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | string

export interface JobStatus {
  job_id: string
  status: JobState
  progress: number
  current_step: string
  result: Record<string, unknown> | null
  error: string | null
}

// ── 내부 fetch 헬퍼 ───────────────────────────────────────────────
// Next API Route(proxy) 경유. 절대 경로(NEXT_PUBLIC_API_BASE_URL)는
// 서버사이드 폴백/직접 호출이 필요할 때만 쓴다.

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    })
  } catch {
    throw new ApiError(
      "백엔드 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.",
      0,
    )
  }

  if (!res.ok) {
    let detail = `요청 실패 (${res.status})`
    try {
      const body = await res.json()
      if (body?.detail) detail = String(body.detail)
      else if (body?.error) detail = String(body.error)
    } catch {
      // JSON 아님 — 기본 메시지 유지
    }
    throw new ApiError(detail, res.status)
  }

  return res.json() as Promise<T>
}

// ── 엔드포인트 (Next proxy 라우트 경유) ───────────────────────────

export async function healthCheck(): Promise<{ status: string }> {
  return request<{ status: string }>("/api/health")
}

export async function generateScenario(params: {
  country: string
  duration_min: number
}): Promise<ScenarioResponse> {
  return request<ScenarioResponse>("/api/storyboard/scenario", {
    method: "POST",
    body: JSON.stringify(params),
  })
}

export async function generateStoryboard(
  params: StoryboardGenerateParams,
): Promise<{ job_id: string; status: string }> {
  return request<{ job_id: string; status: string }>(
    "/api/storyboard/generate",
    { method: "POST", body: JSON.stringify(params) },
  )
}

export async function regenerateScene(
  params: SceneRegenerateParams,
): Promise<{ job_id: string; status: string }> {
  return request<{ job_id: string; status: string }>(
    "/api/storyboard/regenerate",
    { method: "POST", body: JSON.stringify(params) },
  )
}

export async function startVideo(
  params: VideoStartParams,
): Promise<{ job_id: string; status: string }> {
  return request<{ job_id: string; status: string }>("/api/video/start", {
    method: "POST",
    body: JSON.stringify(params),
  })
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  return request<JobStatus>(`/api/jobs/${jobId}/status`)
}

// ── 폴링 헬퍼 ─────────────────────────────────────────────────────
// jobId 상태를 intervalMs 마다 조회. completed/failed 시 자동 중단.
// 반환값을 호출하면 폴링을 강제 중단(cleanup)한다.

export function pollJobStatus(
  jobId: string,
  onUpdate: (status: JobStatus) => void,
  intervalMs = 2000,
  onError?: (error: ApiError) => void,
): () => void {
  let stopped = false
  let timer: ReturnType<typeof setTimeout> | null = null

  const tick = async () => {
    if (stopped) return
    try {
      const status = await getJobStatus(jobId)
      if (stopped) return
      onUpdate(status)
      if (status.status === "completed" || status.status === "failed") {
        stopped = true
        return
      }
    } catch (err) {
      if (stopped) return
      if (onError) onError(err instanceof ApiError ? err : new ApiError(String(err), 0))
      // 일시적 네트워크 오류일 수 있으니 폴링은 계속한다.
    }
    if (!stopped) timer = setTimeout(tick, intervalMs)
  }

  tick()

  return () => {
    stopped = true
    if (timer) clearTimeout(timer)
  }
}
