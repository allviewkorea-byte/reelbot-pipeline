// 작업 종류별 fetch timeout 상수.
// 콘티/이미지/영상 생성은 OpenAI gpt-image-1 다중 호출 등으로 수 분이 걸리므로
// 일반 조회(QUICK)와 분리해서 충분히 긴 timeout 을 적용한다.
export const TIMEOUT = {
  HEALTH: 8_000, // 헬스체크: 8초
  QUICK: 30_000, // 일반 조회/저장: 30초
  HEAVY: 300_000, // 콘티/이미지 생성: 5분
  VERY_HEAVY: 600_000, // 영상 생성 등: 10분
} as const

export function withTimeout(ms: number): RequestInit {
  return { signal: AbortSignal.timeout(ms) }
}
