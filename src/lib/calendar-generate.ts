// 캘린더 롤링 자동 생성(7b) — 트렌드 근거로 하루 3슬롯 컨셉을 자동 배정하는 '순수 로직'.
// DB·트렌드 fetch 는 API 라우트가 담당하고, 여기는 가중 추첨 + 규칙만(테스트 쉽게).
// 매일 자동 실행(스케줄러)은 7c.

import {
  CONTENT_CONCEPTS,
  CONTENT_SLOTS,
  CONCEPT_CONFLICT_WINDOW_DAYS,
  randomSlotTime,
  type ContentSlot,
  type SlotDef,
} from "./content-plan"
import type { TrendRankingItem } from "./trend-concepts"

// share 0 컨셉도 아주 가끔은 뽑히게(완전 배제 X) — 다양성 확보용 바닥 가중치.
const CONCEPT_FLOOR = 0.02

// 한 컨셉이 생성 기간 전체에서 차지할 수 있는 최대 비율(쏠림 완화). 조정 쉽게 상수로.
// 예: 30일×3슬롯=90칸 × 0.30 = 27칸 상한. 트렌드 상위라도 이 이상은 안 뽑힘.
export const CONCEPT_SHARE_CAP = 0.3

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

// 한 슬롯 컨셉 선택: exclude(하루 중복·상한 도달) 하드 제외, avoid(±N일) 회피, 가중 랜덤.
// 회피로 후보가 0이 되면 회피를 완화하고, 그래도 0이면 최후로 전체 허용(하루 중복은
// exclude 에 sameDay 만 넣고 호출하면 끝까지 유지됨 — 상한은 최후에만 무시).
export function pickConcept(
  weights: Record<string, number>,
  exclude: Set<string>,
  avoid: Set<string>,
): string {
  const all = CONTENT_CONCEPTS as readonly string[]
  let candidates = all.filter((c) => !exclude.has(c) && !avoid.has(c))
  if (candidates.length === 0) candidates = all.filter((c) => !exclude.has(c)) // ±N일 회피 완화
  if (candidates.length === 0) candidates = [...all] // 최후(상한·회피 모두 무시)
  return weightedPick(weights, candidates) ?? "기타"
}

export interface SlotAssignment {
  slot: ContentSlot
  concept: string
  scheduled_time: string // HH:MM
}

// 하루의 '빈 슬롯'만 컨셉·시각 배정(채워진 슬롯은 호출부가 제외해 전달 → 보존).
// sameDayConcepts: 그 날 이미 쓰인 컨셉(수동분 포함, 하루 중복 금지). recentConcepts: ±N일.
// counts/capCount: 컨셉 쏠림 완화 — counts(전 기간 누적, mutate)가 capCount 도달한 컨셉은
//   후보에서 제외. (counts 미전달 시 상한 미적용 = 기존 동작)
// 배열에서 k개를 무작위로(중복 없이) 뽑는다(부분 Fisher-Yates). k>=length 면 원본 순서 유지.
function sampleK<T>(arr: T[], k: number): T[] {
  if (k >= arr.length) return arr.slice() // 전체 선택 = 순서 보존(cap=3 현행 동작 유지)
  const a = arr.slice()
  for (let i = 0; i < k; i++) {
    const j = i + Math.floor(Math.random() * (a.length - i))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a.slice(0, k)
}

// 하루의 '빈 슬롯'을 daily_cap 만큼 채운다(채워진 슬롯은 호출부가 제외해 전달 → 보존).
// ★카테고리 = "그날 3슬롯이 받았을 후보 3개를 기존 로직대로 계산한 뒤, 빈 슬롯 수만큼 무작위 선택".
//   시간대(slots)와 카테고리(후보 중 랜덤) 두 축을 분리한다. cap=3(빈 슬롯 3개)이면 후보 3개를
//   순서대로 배정 = 현행 그대로.
// sameDayConcepts: 그 날 이미 쓰인 컨셉(수동분 포함, 하루 중복 금지). recentConcepts: ±N일.
// counts/capCount: 컨셉 쏠림 완화 — 후보 계산 시 capCount 도달 컨셉 제외, 실제 확정분만 누적.
export function planCappedSlots(opts: {
  filledSlots: Set<ContentSlot>
  sameDayConcepts: Set<string>
  recentConcepts: Set<string>
  weights: Record<string, number>
  counts?: Map<string, number>
  capCount?: number
  slots: SlotDef[] // 채울 시간대(slotsForCap)
}): SlotAssignment[] {
  // 1) 채울 빈 시간대(이미 찬 슬롯 제외).
  const emptySlots = opts.slots.filter((s) => !opts.filledSlots.has(s.id))
  if (emptySlots.length === 0) return []

  // 2) '그날의 후보 카테고리'를 3개(=하루 최대 슬롯 수) 기존 로직대로 계산(서로 다른 가중랜덤).
  const sameDay = new Set(opts.sameDayConcepts)
  const counts = opts.counts
  const capCount = opts.capCount ?? 0
  const candidates: string[] = []
  for (let i = 0; i < CONTENT_SLOTS.length; i++) {
    const exclude = new Set(sameDay)
    if (counts && capCount > 0) {
      for (const [c, n] of counts) if (n >= capCount) exclude.add(c)
    }
    const concept = pickConcept(opts.weights, exclude, opts.recentConcepts)
    candidates.push(concept)
    sameDay.add(concept) // 후보끼리 서로 다른 컨셉
  }

  // 3) 후보 중 빈 슬롯 수만큼 무작위 선택 → 시간대에 배정(확정분만 counts 누적).
  const chosen = sampleK(candidates, emptySlots.length)
  const out: SlotAssignment[] = []
  emptySlots.forEach((s, i) => {
    const concept = chosen[i]
    if (counts) counts.set(concept, (counts.get(concept) ?? 0) + 1)
    out.push({ slot: s.id, concept, scheduled_time: randomSlotTime(s.id) })
  })
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
