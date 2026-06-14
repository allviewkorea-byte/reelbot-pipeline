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

export type ContentPlanStatus = "planned" | "done" | "skipped"

export interface ContentPlan {
  id: string
  channel_id: string
  date: string // YYYY-MM-DD (발행 예정일)
  concept: string
  title: string | null
  status: ContentPlanStatus
  memo: string | null
  created_at?: string
}

// 연속 컨셉 감지 범위(앞뒤 N일).
export const CONCEPT_CONFLICT_WINDOW_DAYS = 3
