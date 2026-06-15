// 캘린더 생성 오케스트레이션 — POST /api/calendar/generate 와 GET /api/cron/roll 가 공유.
// (7b 로직을 함수로 추출. 동작 동일 — 알고리즘 변경 없음.)
import { type ContentPlan, type ContentSlot } from "./content-plan"
import { listContentPlans, upsertContentPlans, getTrendRanking } from "./supabase"
import { todayKST } from "./trend-concepts"
import {
  buildConceptWeights,
  planEmptySlots,
  isoFromKSTOffset,
  addDaysISO,
  neighborDates,
  CONCEPT_SHARE_CAP,
} from "./calendar-generate"

export type GenerateMode = "fill30" | "rollOne"

export interface GenerateResult {
  mode: GenerateMode
  channelId: string
  trendSource: string
  daysProcessed: number
  slotsCreated: number
  dates: string[]
}

// 멱등: 이미 있는(수동 포함) 슬롯은 보존, 빈 슬롯만 채움 → 중복 호출 안전.
export async function generateCalendar(mode: GenerateMode, channelId: string): Promise<GenerateResult> {
  // 대상 날짜: fill30 = 0..29, rollOne = 30.
  const offsets = mode === "rollOne" ? [30] : Array.from({ length: 30 }, (_, i) => i)
  const targetDates = offsets.map((o) => isoFromKSTOffset(o)).sort()

  // 쏠림 완화 기준 '분포 구간'. fill30 = 대상 30일. rollOne = 최근 30일(롤링 day 기준).
  const distributionDates =
    mode === "rollOne"
      ? Array.from({ length: 30 }, (_, i) => isoFromKSTOffset(i + 1)) // offsets 1..30
      : targetDates
  const distSet = new Set(distributionDates)
  const capCount = Math.ceil(CONCEPT_SHARE_CAP * distributionDates.length * 3)

  // 1) 트렌드 가중치(오늘 캐시 1회 재사용). 없으면 null → 균등 폴백.
  const ranking = await getTrendRanking(channelId, todayKST())
  const weights = buildConceptWeights(ranking?.rankings ?? null)

  // 2) ±N일 회피·하루중복·수동 보존·분포(상한) 판단용 기존 plans 조회.
  const bounds = [
    ...distributionDates,
    addDaysISO(targetDates[0], -4),
    addDaysISO(targetDates[targetDates.length - 1], 4),
  ]
  const from = bounds.reduce((a, b) => (a < b ? a : b))
  const to = bounds.reduce((a, b) => (a > b ? a : b))
  const existing = await listContentPlans(channelId, from, to)

  const usageByDate = new Map<string, Set<string>>()
  const slotsByDate = new Map<string, Set<ContentSlot>>()
  const counts = new Map<string, number>()
  for (const p of existing) {
    if (!usageByDate.has(p.date)) usageByDate.set(p.date, new Set())
    if (p.concept) usageByDate.get(p.date)!.add(p.concept)
    if (!slotsByDate.has(p.date)) slotsByDate.set(p.date, new Set())
    slotsByDate.get(p.date)!.add((p.slot ?? "morning") as ContentSlot)
    if (p.concept && distSet.has(p.date)) counts.set(p.concept, (counts.get(p.concept) ?? 0) + 1)
  }

  // 3) 날짜순으로 빈 슬롯 채우기.
  const newRows: ContentPlan[] = []
  for (const date of targetDates) {
    const filledSlots = slotsByDate.get(date) ?? new Set<ContentSlot>()
    const sameDayConcepts = usageByDate.get(date) ?? new Set<string>()
    const recentConcepts = new Set<string>()
    for (const nb of neighborDates(date)) {
      for (const c of usageByDate.get(nb) ?? []) recentConcepts.add(c)
    }

    const assignments = planEmptySlots({
      filledSlots,
      sameDayConcepts,
      recentConcepts,
      weights,
      counts,
      capCount,
    })

    if (!usageByDate.has(date)) usageByDate.set(date, new Set())
    for (const a of assignments) {
      newRows.push({
        id: crypto.randomUUID(),
        channel_id: channelId,
        date,
        slot: a.slot,
        scheduled_time: a.scheduled_time,
        concept: a.concept,
        title: null,
        status: "planned",
        memo: null,
      })
      usageByDate.get(date)!.add(a.concept) // 이후 날짜의 ±N일 회피에 반영
    }
  }

  // 4) 일괄 저장.
  await upsertContentPlans(newRows)

  return {
    mode,
    channelId,
    trendSource: ranking?.source ?? "fallback",
    daysProcessed: targetDates.length,
    slotsCreated: newRows.length,
    dates: targetDates,
  }
}
