// 캘린더 롤링 자동 생성(7b) — 트렌드 근거로 하루 3슬롯 컨셉을 자동 배정하는 '순수 로직'.
// DB·트렌드 fetch 는 API 라우트가 담당하고, 여기는 가중 추첨 + 규칙만(테스트 쉽게).
// 매일 자동 실행(스케줄러)은 7c.

import {
  CONTENT_CONCEPTS,
  CONTENT_SLOTS,
  CONCEPT_CONFLICT_WINDOW_DAYS,
  randomSlotTime,
  type ContentSlot,
} from "./content-plan"
import type { TrendRankingItem } from "./trend-concepts"

// share 0 컨셉도 아주 가끔은 뽑히게(완전 배제 X) — 다양성 확보용 바닥 가중치.
const CONCEPT_FLOOR = 0.02

// 트렌드 랭킹 → 컨셉별 가중치. 랭킹 없으면 전부 floor(=균등) → 폴백이 자동.
export function buildConceptWeights(rankings: TrendRankingItem[] | null): Record<string, number> {
  const w: Record<string, number> = {}
  for (const c of CONTENT_CONCEPTS) w[c] = CONCEPT_FLOOR
  if (rankings) {
    for (const r of rankings) {
      if (w[r.concept] !== undefined) w[r.concept] = CONCEPT_FLOOR + Math.max(0, r.share)
    }
  }
  return w
}

// 후보 중 가중 랜덤 1개.
function weightedPick(weights: Record<string, number>, candidates: string[]): string | null {
  if (candidates.length === 0) return null
  const total = candidates.reduce((s, c) => s + Math.max(0, weights[c] ?? 0), 0)
  if (total <= 0) return candidates[Math.floor(Math.random() * candidates.length)]
  let r = Math.random() * total
  for (const c of candidates) {
    r -= Math.max(0, weights[c] ?? 0)
    if (r <= 0) return c
  }
  return candidates[candidates.length - 1]
}

// 한 슬롯 컨셉 선택: 같은 날(sameDay) 제외, ±N일(recent) 회피, 가중 랜덤.
// 연속 회피로 후보가 0이 되면 회피를 완화(하루 중복 금지는 끝까지 지킴).
export function pickConcept(
  weights: Record<string, number>,
  sameDay: Set<string>,
  recent: Set<string>,
): string {
  const all = CONTENT_CONCEPTS as readonly string[]
  let candidates = all.filter((c) => !sameDay.has(c) && !recent.has(c))
  if (candidates.length === 0) candidates = all.filter((c) => !sameDay.has(c)) // ±N일 회피 완화
  if (candidates.length === 0) candidates = [...all] // 최후
  return weightedPick(weights, candidates) ?? "기타"
}

export interface SlotAssignment {
  slot: ContentSlot
  concept: string
  scheduled_time: string // HH:MM
}

// 하루의 '빈 슬롯'만 컨셉·시각 배정(채워진 슬롯은 호출부가 제외해 전달 → 보존).
// sameDayConcepts: 그 날 이미 쓰인 컨셉(수동분 포함, 하루 중복 금지). recentConcepts: ±N일.
export function planEmptySlots(opts: {
  filledSlots: Set<ContentSlot>
  sameDayConcepts: Set<string>
  recentConcepts: Set<string>
  weights: Record<string, number>
}): SlotAssignment[] {
  const sameDay = new Set(opts.sameDayConcepts)
  const out: SlotAssignment[] = []
  for (const s of CONTENT_SLOTS) {
    if (opts.filledSlots.has(s.id)) continue
    const concept = pickConcept(opts.weights, sameDay, opts.recentConcepts)
    sameDay.add(concept) // 같은 날 다음 슬롯은 다른 컨셉
    out.push({ slot: s.id, concept, scheduled_time: randomSlotTime(s.id) })
  }
  return out
}

// ── 날짜 헬퍼(KST 기준, 순수 문자열 연산) ────────────────────────────
// KST 오늘에서 days 만큼 떨어진 'YYYY-MM-DD'. (서버가 UTC 여도 한국 일자 기준)
export function isoFromKSTOffset(days: number): string {
  const base = new Date(Date.now() + 9 * 3600 * 1000) // UTC 필드 = KST 벽시계
  base.setUTCDate(base.getUTCDate() + days)
  return base.toISOString().slice(0, 10)
}

// 'YYYY-MM-DD' + n일.
export function addDaysISO(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

// ±N일 회피 윈도우 일자들(중심 제외).
export function neighborDates(iso: string): string[] {
  const out: string[] = []
  for (let k = -CONCEPT_CONFLICT_WINDOW_DAYS; k <= CONCEPT_CONFLICT_WINDOW_DAYS; k++) {
    if (k !== 0) out.push(addDaysISO(iso, k))
  }
  return out
}
