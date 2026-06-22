// 음악 채널(Revezen/루프탑뮤직) 전용 상수·헬퍼 — 백곰 코드와 분리(컴포넌트 import 금지, 패턴만 차용).

// channel_status 테이블의 음악 채널 row 키(백곰 'baekgom'과 분리, 같은 테이블·같은 컬럼 재사용).
export const MUSIC_CHANNEL_ID = "rooftop_music"

export const MUSIC_CHANNEL_NAME =
  process.env.NEXT_PUBLIC_MUSIC_CHANNEL_NAME || "Revezen"

// 큰 수 → 한국어 단위(백곰 fmtCount 패턴 차용, import 금지·자체 구현).
export function fmtCount(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—"
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}억`
  if (n >= 10_000) return `${(n / 10_000).toFixed(1)}만`
  return n.toLocaleString("ko-KR")
}

export interface MusicMetrics {
  subscriberCount: number | null
  viewCount: number | null
  videoCount: number | null
  averageViews: number | null
  error?: boolean
}
