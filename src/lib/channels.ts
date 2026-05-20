export type Platform = "youtube" | "instagram" | "tiktok" | "naverclip"
export type ContentType = "long" | "short"
export type Track = "auto" | "semi" | "adobe"
export type StatusVariant = "active" | "growing" | "pending"

export const PLATFORM_LABELS: Record<Platform, string> = {
  youtube: "유튜브",
  instagram: "인스타그램",
  tiktok: "틱톡",
  naverclip: "네이버클립",
}

// 플랫폼 뱃지 색상 — 기존 톤(빨강/핑크/검정/초록)을 Tailwind 기본 유틸로 표현
export const PLATFORM_BADGE: Record<Platform, string> = {
  youtube: "bg-red-500/15 text-red-400",
  instagram: "bg-pink-500/15 text-pink-400",
  tiktok: "bg-neutral-500/20 text-neutral-300",
  naverclip: "bg-emerald-500/15 text-emerald-400",
}

export const TRACK_LABELS: Record<Track, string> = {
  auto: "자동화",
  semi: "반자동",
  adobe: "어도비 편집",
}

export const TRACK_BADGE: Record<Track, string> = {
  auto: "bg-primary/15 text-primary",
  semi: "bg-sky-500/15 text-sky-400",
  adobe: "bg-amber-500/15 text-amber-400",
}

export const SCENARIO_TONES = ["여행", "일상", "분석", "정성", "리뷰"] as const

export const STORYBOARD_MODELS = [
  { value: "gpt-image-1", label: "gpt-image-1 (현재)", disabled: false },
  { value: "z-image-turbo", label: "Z-Image Turbo (Phase 3 예정)", disabled: true },
] as const

export const VIDEO_MODELS = [
  { value: "kling-v1", label: "Kling v1 (현재)", disabled: false },
  { value: "kling-v3", label: "Kling v3 + Character ID (Phase 3 예정)", disabled: true },
] as const

export const SUBTITLE_STYLES = [
  { value: "basic", label: "기본" },
  { value: "caption", label: "캡션" },
  { value: "subtitle", label: "자막" },
] as const

export interface StackConfig {
  track: Track
  characters: string[]
  scenarioTone: string
  storyboardModel: string
  videoModel: string
  subtitleStyle: string
  publishTargets: Platform[]
  schedule: string
  contentType: ContentType
  ratio: string
  ratioOverride: boolean
}

export interface Channel {
  id: string
  name: string
  platform: Platform
  character: string
  subscribers: string
  videos: number
  revenue: number
  avgViews: string
  status: string
  statusVariant: StatusVariant
  color: string
  stack: StackConfig
}

// 작업 2.5-5 · 플랫폼별 비율 자동 매핑
export function getDefaultRatio(platform: Platform, contentType: ContentType): string {
  if (platform === "youtube") {
    return contentType === "long" ? "16:9" : "9:16"
  }
  // 인스타그램 릴스 / 틱톡 / 네이버클립 → 세로
  return "9:16"
}

export const DEFAULT_CHANNELS: Channel[] = [
  {
    id: "bangkok",
    name: "방콕 여행 채널",
    platform: "youtube",
    character: "지수",
    subscribers: "2.1K",
    videos: 54,
    revenue: 68,
    avgViews: "1.2K",
    status: "활성",
    statusVariant: "active",
    color: "#8b5cf6",
    stack: {
      track: "auto",
      characters: ["지수"],
      scenarioTone: "여행",
      storyboardModel: "gpt-image-1",
      videoModel: "kling-v1",
      subtitleStyle: "basic",
      publishTargets: ["youtube"],
      schedule: "매일 09시",
      contentType: "long",
      ratio: "16:9",
      ratioOverride: false,
    },
  },
  {
    id: "tokyo",
    name: "도쿄 일상 브이로그",
    platform: "instagram",
    character: "하은",
    subscribers: "1.8K",
    videos: 48,
    revenue: 42,
    avgViews: "890",
    status: "활성",
    statusVariant: "active",
    color: "#06b6d4",
    stack: {
      track: "semi",
      characters: ["하은"],
      scenarioTone: "일상",
      storyboardModel: "gpt-image-1",
      videoModel: "kling-v1",
      subtitleStyle: "caption",
      publishTargets: ["instagram"],
      schedule: "주 3회",
      contentType: "short",
      ratio: "9:16",
      ratioOverride: false,
    },
  },
  {
    id: "europe",
    name: "유럽 감성 여행",
    platform: "youtube",
    character: "지수",
    subscribers: "890",
    videos: 25,
    revenue: 17,
    avgViews: "420",
    status: "준비 중",
    statusVariant: "pending",
    color: "#f59e0b",
    stack: {
      track: "adobe",
      characters: ["지수"],
      scenarioTone: "정성",
      storyboardModel: "gpt-image-1",
      videoModel: "kling-v1",
      subtitleStyle: "subtitle",
      publishTargets: ["youtube"],
      schedule: "주 1회",
      contentType: "long",
      ratio: "16:9",
      ratioOverride: false,
    },
  },
]

export const PLATFORM_ORDER: Platform[] = ["youtube", "instagram", "tiktok", "naverclip"]

export const CHARACTER_OPTIONS = ["지수", "하은", "준혁", "서연"]
