// 캘린더 생성 오케스트레이션 — POST /api/calendar/generate 와 GET /api/cron/roll 가 공유.
// (7b 로직을 함수로 추출. 동작 동일 — 알고리즘 변경 없음.)
import {
  type ContentPlan,
  type ContentSlot,
  slotsForCap,
} from "./content-plan"
import {
  listContentPlans,
  upsertContentPlans,
  deleteContentPlan,
  getTrendRanking,
  getChannelStatus,
} from "./supabase"
import { todayKST } from "./trend-concepts"
import {
  buildConceptWeights,
  planCappedSlots,
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

  // 0) 하루 생산 개수(daily_cap) → 채울 시간 슬롯 결정(cap=1 저녁 / 2 저녁+밤 / 3 현행).
  const { dailyCap } = await getChannelStatus(channelId)
  const slots = slotsForCap(dailyCap)

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

    const assignments = planCappedSlots({
      filledSlots,
      sameDayConcepts,
      recentConcepts,
      weights,
      counts,
      capCount,
      slots, // daily_cap 시간대; 카테고리는 후보 중 랜덤
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

// daily_cap 변경 시: 오늘 이후 **미제작 날짜만** 새 cap 개수로 재생성한다.
// ★안전: 과거(오늘 이전) 날짜는 손대지 않음. done(제작완료) 슬롯이 하나라도 있는 날짜는
//   통째로 보존(삭제/변경 금지). 미제작(planned만) 날짜만: 원치 않는 슬롯 삭제 + 부족분 추가.
export async function applyCapToFuture(
  channelId: string,
  cap: number,
): Promise<{ datesChanged: number; slotsCreated: number; slotsDeleted: number }> {
  const today = todayKST()
  const end = isoFromKSTOffset(30)
  const wanted = slotsForCap(cap)
  const wantedIds = new Set(wanted.map((s) => s.id))

  const ranking = await getTrendRanking(channelId, today)
  const weights = buildConceptWeights(ranking?.rankings ?? null)

  // ±N일 회피·하루중복 판단용으로 기존 plans 를 넉넉히 조회(앞뒤 여유).
  const existing = await listContentPlans(
    channelId,
    addDaysISO(today, -4),
    addDaysISO(end, 4),
  )
  const byDate = new Map<string, ContentPlan[]>()
  const usageByDate = new Map<string, Set<string>>()
  for (const p of existing) {
    if (!byDate.has(p.date)) byDate.set(p.date, [])
    byDate.get(p.date)!.push(p)
    if (!usageByDate.has(p.date)) usageByDate.set(p.date, new Set())
    if (p.concept) usageByDate.get(p.date)!.add(p.concept)
  }

  const toDelete: string[] = []
  const newRows: ContentPlan[] = []
  const changed = new Set<string>()

  for (let o = 0; o <= 30; o++) {
    const date = isoFromKSTOffset(o) // 오늘(0)부터 +30일까지만 — 과거는 절대 미포함
    const rows = byDate.get(date) ?? []
    // done(제작완료) 슬롯이 있는 날짜는 통째로 보존(절대 변경/삭제 금지).
    if (rows.some((r) => r.status === "done")) continue

    // 1) 원치 않는 슬롯(planned)만 삭제 대상으로. (이 날짜엔 done 이 없음이 보장됨)
    const keep: ContentPlan[] = []
    for (const r of rows) {
      const sid = (r.slot ?? "morning") as ContentSlot
      if (wantedIds.has(sid)) keep.push(r)
      else {
        toDelete.push(r.id)
        changed.add(date)
        usageByDate.get(date)?.delete(r.concept) // 회피 계산에서 제거분 반영
      }
    }
    // 2) 부족한 wanted 슬롯 채우기 — 생성과 동일한 '후보 중 랜덤' 로직(planCappedSlots).
    const filledSlots = new Set(keep.map((r) => (r.slot ?? "morning") as ContentSlot))
    const sameDay = new Set(keep.map((r) => r.concept).filter(Boolean) as string[])
    const recent = new Set<string>()
    for (const nb of neighborDates(date)) for (const c of usageByDate.get(nb) ?? []) recent.add(c)

    const assignments = planCappedSlots({
      filledSlots,
      sameDayConcepts: sameDay,
      recentConcepts: recent,
      weights,
      slots: wanted,
    })
    for (const a of assignments) {
      let dayUse = usageByDate.get(date)
      if (!dayUse) {
        dayUse = new Set<string>()
        usageByDate.set(date, dayUse)
      }
      dayUse.add(a.concept) // 이후 날짜 ±N일 회피에 반영
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
      changed.add(date)
    }
  }

  for (const id of toDelete) await deleteContentPlan(id)
  if (newRows.length) await upsertContentPlans(newRows)

  return { datesChanged: changed.size, slotsCreated: newRows.length, slotsDeleted: toDelete.length }
}
