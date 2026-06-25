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

// #41 예상 제작 시간 — 곡수 → 영상 길이 + 제작 단계별 시간(클라이언트 계산, API 호출 없음).
// 상수는 0단계 실측/코드 근거: 곡당 평균 길이 ~4분(music_mix 가정 180s 보다 보수적·#40 UI 4분),
// 크로스페이드 2s(music_mix CROSSFADE_SEC), suno 곡당 순차 ~2분(POLL 상한 900s),
// 믹스 곡수 선형(페어와이즈 N-1), 렌더 영상1초당 ~3초(실측 114s→349s), 업로드 ~3분.
export const EST_SONG_SEC = 240 // 곡당 평균 길이(초) ≈ 4분
export const EST_CROSSFADE_SEC = 2
export const EST_SUNO_MIN_PER_SONG = 2 // suno 곡당 생성 ~2분(순차)
export const EST_MIX_BASE_MIN = 1
export const EST_MIX_MIN_PER_SONG = 0.1
export const EST_RENDER_RATIO = 3 // 영상 1초당 렌더 ~3초
export const EST_UPLOAD_MIN = 3
export const CREDITS_PER_SONG = 12 // suno 1호출=12크레딧(=2클립, 1곡 사용)
export const CREDIT_USD = 0.005

export interface ProductionEstimate {
  videoMinutes: number
  sunoMinutes: number
  mixMinutes: number
  renderMinutes: number
  uploadMinutes: number
  totalMinutes: number
  credits: number
  costUsd: number
}

export function estimateProductionTime(trackCount: number): ProductionEstimate {
  const n = Math.max(1, Math.floor(trackCount) || 1)
  const videoSec = Math.max(EST_SONG_SEC, n * EST_SONG_SEC - (n - 1) * EST_CROSSFADE_SEC)
  const sunoMinutes = n * EST_SUNO_MIN_PER_SONG
  const mixMinutes = EST_MIX_BASE_MIN + n * EST_MIX_MIN_PER_SONG
  const renderMinutes = (videoSec * EST_RENDER_RATIO) / 60
  const uploadMinutes = EST_UPLOAD_MIN
  return {
    videoMinutes: videoSec / 60,
    sunoMinutes,
    mixMinutes,
    renderMinutes,
    uploadMinutes,
    totalMinutes: sunoMinutes + mixMinutes + renderMinutes + uploadMinutes,
    credits: n * CREDITS_PER_SONG,
    costUsd: n * CREDITS_PER_SONG * CREDIT_USD,
  }
}

// 분 → "약 N시간 M분" / "약 N분".
export function fmtMinutes(m: number): string {
  const total = Math.max(0, Math.round(m))
  if (total < 60) return `약 ${total}분`
  const h = Math.floor(total / 60)
  const mm = total % 60
  return mm ? `약 ${h}시간 ${mm}분` : `약 ${h}시간`
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
  "Bodoni Moda", "Young Serif", "Literata",
] as const

// 한글 폰트 프리셋(제목·부제 한글 글자 fallback). 영어 폰트 뒤 스택으로 적용.
export const DESIGN_PRESET_FONTS_KR = [
  "Noto Serif KR", "Black Han Sans", "Nanum Myeongjo",
] as const
export const DESIGN_KR_FONT_DEFAULT = "Noto Serif KR"

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
  italic?: boolean // #36 title/subtitle 만 사용
  border: TextBorder
}
export interface MusicDesignConfig {
  play_list: TextStyleConfig
  where_label: TextStyleConfig
  title: TextStyleConfig    // #36 곡 제목(좌하단)
  subtitle: TextStyleConfig // #36 부제(좌하단)
  // 인라인 편집 텍스트(빈값=기본값 폴백). playlist_text/where_text=영상 반영, preview_*=미리보기 전용.
  playlist_text?: string
  where_text?: string
  where_label_hidden?: boolean // Where 라벨 영상 숨김(기본 true=숨김)
  title_font_kr?: string // 제목 한글 폰트(기본 Noto Serif KR)
  subtitle_font_kr?: string // 부제 한글 폰트(기본 Noto Serif KR)
  preview_title?: string
  preview_subtitle?: string
}

// 미리보기 기본 텍스트(빈 값일 때 표시). playlist/where 는 Remotion 도 같은 기본값으로 폴백.
export const DESIGN_TEXT_DEFAULTS = {
  playlist_text: "PLAY LIST",
  where_text: "Where",
  preview_title: "시티팝 드라이브",
  preview_subtitle: "morning light on endless urban roads",
} as const

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
  title: {
    font_family: "Playfair Display", font_size: 84, font_weight: 700,
    color: "#FFFFFF", opacity: 1.0, italic: false, border: { enabled: false, width: 1, color: "#000000" },
  },
  subtitle: {
    font_family: "Playfair Display", font_size: 38, font_weight: 400,
    color: "#FFFFFF", opacity: 1.0, italic: true, border: { enabled: false, width: 1, color: "#000000" },
  },
}
