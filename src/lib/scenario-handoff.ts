// 시나리오 → 영상 제작/콘티 생성 페이지로 입력값을 넘기기 위한 핸드오프 헬퍼.
// sessionStorage 에 임시 저장하고, 도착 페이지에서 폼을 자동으로 채운다.
export interface ScenarioHandoffScene {
  title: string
  description: string
  script: string // TTS용 내레이션 텍스트
  durationSec: number // 예상 발화 길이 (초)
}

export interface ScenarioHandoff {
  scenarioId?: string
  topic: string // 소재
  duration: number // 초 단위
  format: "shorts" | "long"
  channelId?: string
  characterIds?: string[]
  titleCandidates?: string[]
  description?: string
  hashtags?: {
    primary?: string[]
    variation?: string[]
    competitor?: string[]
    broad?: string[]
    detail?: string[]
  }
  scenes?: ScenarioHandoffScene[]
  trendId?: string
  createdAt: number
}

const STORAGE_KEY = "reelbot.scenarioHandoff"
const MAX_AGE_MS = 30 * 60 * 1000 // 30분

export function saveScenarioHandoff(data: Omit<ScenarioHandoff, "createdAt">) {
  if (typeof window === "undefined") return
  const payload: ScenarioHandoff = { ...data, createdAt: Date.now() }
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
  } catch {
    /* 저장 실패는 무시 */
  }
}

export function loadScenarioHandoff(): ScenarioHandoff | null {
  if (typeof window === "undefined") return null
  let raw: string | null
  try {
    raw = sessionStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as ScenarioHandoff
    // 오래된 잔여물 방지: 30분 지난 데이터는 폐기
    if (Date.now() - parsed.createdAt > MAX_AGE_MS) {
      clearScenarioHandoff()
      return null
    }
    return parsed
  } catch {
    return null
  }
}

export function clearScenarioHandoff() {
  if (typeof window === "undefined") return
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    /* 무시 */
  }
}
