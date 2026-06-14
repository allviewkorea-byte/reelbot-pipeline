// 트렌드 컨셉 분류 엔진(7a-1) 공유 로직 — 유튜브 인기 숏폼 제목을 사연 9컨셉으로
// 분류하고 조회수 가중 랭킹을 만든다. React 의존 없음(서버 라우트·lib 에서 사용).
// 화면 표시(패널)는 7a-2.

import { CONTENT_CONCEPTS } from "./content-plan"

export type TrendSource = "gpt" | "keyword" | "empty"

// 분류 입력 1건(유튜브 인기 숏폼에서 추출).
export interface ClassifyInput {
  title: string
  viewCount: number
}

// 컨셉별 분류 결과 1건.
export interface ClassifiedItem {
  concept: string
  title: string
  viewCount: number
}

// 9컨셉 랭킹 1줄.
export interface TrendRankingItem {
  concept: string
  score: number // 조회수 가중 합
  share: number // 0~1 (전체 대비 비중)
  sampleTitles: string[] // 대표 제목(조회수 상위 3)
  reason?: string // "왜 떴는지" 한 줄(GPT, 7a-2 표시용)
}

// Supabase trend_rankings 행 + API 반환 형태.
export interface TrendRankingRow {
  id: string // `${channel_id}_${date}`
  channel_id: string
  date: string // YYYY-MM-DD (KST)
  source: TrendSource
  rankings: TrendRankingItem[]
  created_at?: string
}

// ── 키워드 룰 사전(폴백) ─────────────────────────────────────────────
// GPT 실패/키 없음 시 제목 부분일치로 분류. "기타"는 키워드 없이 최종 폴백.
// 한 곳에서 관리(확장 쉽게). 컨셉 키는 CONTENT_CONCEPTS 와 동일 문자열.
export const CONCEPT_KEYWORDS: Record<string, string[]> = {
  가족: ["가족", "엄마", "아빠", "부모", "딸", "아들", "남매", "형제", "자매", "시댁", "며느리", "친정", "할머니", "할아버지"],
  이별: ["이별", "헤어", "헤어졌", "차였", "전남친", "전여친", "재회", "바람", "환승"],
  복수: ["복수", "응징", "사이다", "당했", "되갚", "신고", "처벌", "고소", "참교육"],
  "우정/배신": ["친구", "우정", "배신", "손절", "뒤통수", "절교", "무리"],
  연애: ["연애", "썸", "고백", "남친", "여친", "짝사랑", "소개팅", "데이트", "고백", "커플"],
  "직장/돈": ["직장", "회사", "상사", "퇴사", "월급", "연봉", "빚", "사기", "돈", "부자", "알바", "면접", "사장"],
  감동: ["감동", "눈물", "울컥", "효도", "따뜻", "사연", "기적"],
  반전: ["반전", "알고보니", "충격", "소름", "결말", "정체"],
  기타: [],
}

// ── 키워드 분류(폴백) ────────────────────────────────────────────────
export function classifyByKeywords(items: ClassifyInput[]): ClassifiedItem[] {
  return items.map((it) => {
    const title = it.title ?? ""
    let matched = "기타"
    for (const concept of CONTENT_CONCEPTS) {
      if (concept === "기타") continue
      const kws = CONCEPT_KEYWORDS[concept] ?? []
      if (kws.some((k) => k && title.includes(k))) {
        matched = concept
        break
      }
    }
    return { concept: matched, title, viewCount: it.viewCount }
  })
}

// 입력 concept 가 9컨셉에 없으면 "기타" 로 정규화.
export function normalizeConcept(concept: string): string {
  return (CONTENT_CONCEPTS as readonly string[]).includes(concept) ? concept : "기타"
}

// ── 조회수 가중 랭킹 집계 ────────────────────────────────────────────
// 분류 결과 → 컨셉별 score(조회수 합)·share·대표제목. 등장한 컨셉만, score 내림차순.
export function buildRankings(
  classified: ClassifiedItem[],
  reasons?: Record<string, string>,
): TrendRankingItem[] {
  const byConcept = new Map<string, ClassifiedItem[]>()
  for (const c of classified) {
    const concept = normalizeConcept(c.concept)
    const arr = byConcept.get(concept) ?? []
    arr.push(c)
    byConcept.set(concept, arr)
  }

  const total = classified.reduce((s, c) => s + (c.viewCount || 0), 0)
  const items: TrendRankingItem[] = []
  for (const [concept, list] of byConcept) {
    const score = list.reduce((s, c) => s + (c.viewCount || 0), 0)
    const sampleTitles = [...list]
      .sort((a, b) => (b.viewCount || 0) - (a.viewCount || 0))
      .slice(0, 3)
      .map((c) => c.title)
      .filter(Boolean)
    items.push({
      concept,
      score,
      share: total > 0 ? score / total : 0,
      sampleTitles,
      reason: reasons?.[concept],
    })
  }
  return items.sort((a, b) => b.score - a.score)
}

// KST 기준 오늘 날짜 'YYYY-MM-DD' (서버가 UTC 여도 한국 채널 기준 일자로 캐싱).
export function todayKST(): string {
  return new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10)
}
