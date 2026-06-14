// 콘텐츠 캘린더(content_plans) 공유 상수·타입. 서버 lib/supabase·API·클라이언트
// 컴포넌트가 함께 import (React 의존 없음 — "use client" 아님).

// 운영 채널은 "백곰의 실화보고서" 1개뿐. DB 에는 이 고정 channel_id 로 저장한다.
// (미래 다채널 확장 시 이 상수만 동적으로 바꾸면 됨.)
export const BAEKGOM_CHANNEL_ID = "baekgom"

// 컨셉 고정 목록 — 한 곳에서만 관리(나중에 수정 쉽게).
export const CONTENT_CONCEPTS = [
  "가족",
  "이별",
  "복수",
  "우정/배신",
  "연애",
  "직장/돈",
  "감동",
  "반전",
  "기타",
] as const

export type ContentConcept = (typeof CONTENT_CONCEPTS)[number]

// ── 하루 3슬롯(시간대) ───────────────────────────────────────────────
// 한 행 = 한 슬롯(하루 최대 3행). 구간 안에서 랜덤 시각을 자동 생성한다.
export type ContentSlot = "morning" | "evening" | "night"

export interface SlotDef {
  id: ContentSlot
  label: string
  startHour: number // 포함
  endHour: number // 제외(이 시각 직전까지)
}

export const CONTENT_SLOTS: SlotDef[] = [
  { id: "morning", label: "아침", startHour: 8, endHour: 10 }, // 08~10시
  { id: "evening", label: "저녁", startHour: 18, endHour: 21 }, // 18~21시
  { id: "night", label: "밤", startHour: 21, endHour: 23 }, // 21~23시
]

export const SLOT_BY_ID: Record<ContentSlot, SlotDef> = Object.fromEntries(
  CONTENT_SLOTS.map((s) => [s.id, s]),
) as Record<ContentSlot, SlotDef>

// 구간 내 랜덤 'HH:MM' (endHour 직전까지). 예: morning → 09:23
export function randomSlotTime(slot: ContentSlot): string {
  const def = SLOT_BY_ID[slot]
  const startMin = def.startHour * 60
  const endMin = def.endHour * 60 // 제외
  const t = startMin + Math.floor(Math.random() * (endMin - startMin))
  const hh = String(Math.floor(t / 60)).padStart(2, "0")
  const mm = String(t % 60).padStart(2, "0")
  return `${hh}:${mm}`
}

// ── 컨셉별 색(다크 네이비에서 또렷하게 구분) ──────────────────────────
// 디자인 토큰(globals) 변경 없이 컴포넌트 스코프 인라인 hex 로만 사용.
// 9종이 서로 확실히 구분되도록 색상환을 고루 배치(Tailwind 400 계열 hex).
export const CONCEPT_COLORS: Record<string, string> = {
  가족: "#fbbf24", // amber
  이별: "#60a5fa", // blue
  복수: "#f87171", // red
  "우정/배신": "#c084fc", // purple
  연애: "#f472b6", // pink
  "직장/돈": "#34d399", // emerald
  감동: "#22d3ee", // cyan
  반전: "#fb923c", // orange
  기타: "#94a3b8", // slate
}

export function conceptColor(concept: string): string {
  return CONCEPT_COLORS[concept] ?? "#94a3b8"
}

export type ContentPlanStatus = "planned" | "done" | "skipped"

export interface ContentPlan {
  id: string
  channel_id: string
  date: string // YYYY-MM-DD (발행 예정일)
  concept: string
  title: string | null
  status: ContentPlanStatus
  memo: string | null
  slot?: ContentSlot | null // 아침/저녁/밤. 옛 데이터(slot 없음)도 방어적으로 허용.
  scheduled_time?: string | null // 'HH:MM' (구간 내 랜덤 자동 생성)
  created_at?: string
}

// 연속 컨셉 감지 범위(앞뒤 N일).
export const CONCEPT_CONFLICT_WINDOW_DAYS = 3
