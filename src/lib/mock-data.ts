export const STATS = [
  {
    id: "revenue",
    label: "이번 달 총 수익",
    value: "$127",
    change: "+$34",
    changeLabel: "지난달 대비",
    positive: true,
  },
  {
    id: "channels",
    label: "운영 채널 수",
    value: "3개",
    change: "모두 활성",
    changeLabel: "",
    positive: true,
  },
  {
    id: "videos",
    label: "총 영상 수",
    value: "127개",
    change: "+3",
    changeLabel: "오늘",
    positive: true,
  },
  {
    id: "subscribers",
    label: "총 구독자 수",
    value: "4.8K",
    change: "+240",
    changeLabel: "이번 달",
    positive: true,
  },
]

export const CHANNELS = [
  {
    id: "bangkok",
    name: "방콕 여행",
    status: "활성",
    statusVariant: "active" as const,
    revenue: 68,
    subscribers: "2.1K",
    videos: 54,
    goal: 100,
    color: "#8b5cf6",
  },
  {
    id: "tokyo",
    name: "도쿄 일상",
    status: "성장 중",
    statusVariant: "growing" as const,
    revenue: 42,
    subscribers: "1.8K",
    videos: 48,
    goal: 100,
    color: "#06b6d4",
  },
  {
    id: "europe",
    name: "유럽 감성",
    status: "성장 중",
    statusVariant: "growing" as const,
    revenue: 17,
    subscribers: "890",
    videos: 25,
    goal: 100,
    color: "#f59e0b",
  },
]

export const CHART_DATA = [
  { name: "방콕 여행", revenue: 68, fill: "#8b5cf6" },
  { name: "도쿄 일상", revenue: 42, fill: "#06b6d4" },
  { name: "유럽 감성", revenue: 17, fill: "#f59e0b" },
]

export const PIPELINE_JOBS = [
  {
    id: 1,
    title: "시나리오 생성",
    subtitle: "도쿄 시부야 · 24장면",
    progress: 78,
    status: "running" as const,
  },
  {
    id: 2,
    title: "영상 클립 생성",
    subtitle: "방콕 왓아룬 · S18/24",
    progress: 75,
    status: "running" as const,
  },
  {
    id: 3,
    title: "유튜브 업로드 대기",
    subtitle: "파리 에펠탑",
    progress: 0,
    status: "waiting" as const,
  },
]
