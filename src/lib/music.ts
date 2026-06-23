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

// #37 채널 설정(슬로건·소셜·AI 명시) — channel_status.channel_config jsonb 에 보관.
export interface MusicChannelConfig {
  slogan_en: string
  slogan_kr: string
  email: string
  instagram: string
  tiktok: string
  spotify_url: string
  ai_disclosure: string
}

export const DEFAULT_AI_DISCLOSURE =
  "💿 모든 음악은 AI 음원 생성 시스템으로 제작한 창작 사운드입니다. 모든 이미지는 AI 생성 또는 라이선스 이미지를 사용합니다."

export const DEFAULT_MUSIC_CONFIG: MusicChannelConfig = {
  slogan_en: "",
  slogan_kr: "",
  email: "",
  instagram: "",
  tiktok: "",
  spotify_url: "",
  ai_disclosure: DEFAULT_AI_DISCLOSURE,
}

// 부분 입력 → 누락 키 기본값 채움(빈 칸 허용, AI 명시는 빈칸이면 기본 문구).
export function normalizeMusicConfig(raw: unknown): MusicChannelConfig {
  const r = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>
  const str = (k: keyof MusicChannelConfig) => (typeof r[k] === "string" ? (r[k] as string) : "")
  return {
    slogan_en: str("slogan_en"),
    slogan_kr: str("slogan_kr"),
    email: str("email"),
    instagram: str("instagram"),
    tiktok: str("tiktok"),
    spotify_url: str("spotify_url"),
    ai_disclosure: str("ai_disclosure").trim() || DEFAULT_AI_DISCLOSURE,
  }
}

// #35-A 디자인 시스템 본부 — PLAY LIST·Where 폰트/크기/두께/색/투명도/테두리.
// 프리셋 폰트 10종(Remotion·프론트 미리보기 공통). 이름은 Google Fonts 패밀리명과 일치.
export const DESIGN_PRESET_FONTS = [
  "Montserrat", "Poppins", "Bebas Neue", "Oswald", "Anton",
  "Archivo", "Inter", "DM Sans", "Playfair Display", "Cormorant Garamond",
] as const

export interface TextBorder {
  enabled: boolean
  width: number
  color: string
}
export interface TextStyleConfig {
  font_family: string
  font_size: number
  font_weight: number
  color: string
  opacity: number
  border: TextBorder
}
export interface MusicDesignConfig {
  play_list: TextStyleConfig
  where_label: TextStyleConfig
}

// UI 초기 기본값(백엔드 default_design_config 와 동일). 저장 전엔 렌더 무영향(MusicViz 가 현재값 폴백).
export const DEFAULT_DESIGN_CONFIG: MusicDesignConfig = {
  play_list: {
    font_family: "Playfair Display", font_size: 324, font_weight: 700,
    color: "#FFFFFF", opacity: 1.0, border: { enabled: false, width: 2, color: "#000000" },
  },
  where_label: {
    font_family: "Inter", font_size: 24, font_weight: 600,
    color: "#FFFFFF", opacity: 0.9, border: { enabled: false, width: 1, color: "#000000" },
  },
}
