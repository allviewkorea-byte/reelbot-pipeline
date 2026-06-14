import { NextRequest, NextResponse } from "next/server"
import { BAEKGOM_CHANNEL_ID, type ContentPlan, type ContentSlot } from "@/lib/content-plan"
import { listContentPlans, upsertContentPlans, getTrendRanking } from "@/lib/supabase"
import { todayKST } from "@/lib/trend-concepts"
import {
  buildConceptWeights,
  planEmptySlots,
  isoFromKSTOffset,
  addDaysISO,
  neighborDates,
} from "@/lib/calendar-generate"

// 캘린더 롤링 자동 생성(7b): 트렌드 근거로 하루 3슬롯 컨셉 자동 배정 → content_plans 저장.
//  - mode=fill30: 오늘~+29일(30일) 초기 채우기
//  - mode=rollOne: +30일(그 1일치) 롤링 — 매일 호출용(7c 스케줄러가 부름)
// 멱등: 이미 있는(수동 포함) 슬롯은 보존, 빈 슬롯만 채움 → 중복 호출 안전.
export const dynamic = "force-dynamic"

type Mode = "fill30" | "rollOne"

export async function POST(req: NextRequest) {
  let body: { mode?: string; channelId?: string }
  try {
    body = await req.json()
  } catch {
    body = {}
  }
  const mode: Mode = body.mode === "rollOne" ? "rollOne" : "fill30"
  const channelId = body.channelId || BAEKGOM_CHANNEL_ID

  // 대상 날짜: fill30 = 0..29, rollOne = 30.
  const offsets = mode === "rollOne" ? [30] : Array.from({ length: 30 }, (_, i) => i)
  const targetDates = offsets.map((o) => isoFromKSTOffset(o)).sort()

  try {
    // 1) 트렌드 가중치(오늘 캐시 1회 재사용). 없으면 null → 균등 폴백.
    const ranking = await getTrendRanking(channelId, todayKST())
    const weights = buildConceptWeights(ranking?.rankings ?? null)

    // 2) ±N일 회피·하루중복·수동 보존 판단용으로 대상±버퍼 구간의 기존 plans 조회.
    const from = addDaysISO(targetDates[0], -4)
    const to = addDaysISO(targetDates[targetDates.length - 1], 4)
    const existing = await listContentPlans(channelId, from, to)

    // 날짜별 사용 컨셉 / 채워진 슬롯 맵(기존 + 생성분 누적).
    const usageByDate = new Map<string, Set<string>>()
    const slotsByDate = new Map<string, Set<ContentSlot>>()
    for (const p of existing) {
      if (!usageByDate.has(p.date)) usageByDate.set(p.date, new Set())
      if (p.concept) usageByDate.get(p.date)!.add(p.concept)
      if (!slotsByDate.has(p.date)) slotsByDate.set(p.date, new Set())
      slotsByDate.get(p.date)!.add((p.slot ?? "morning") as ContentSlot)
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

      const assignments = planEmptySlots({ filledSlots, sameDayConcepts, recentConcepts, weights })

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

    // 4) 일괄 저장(베스트 에포트는 아님 — 실패 시 에러 노출).
    await upsertContentPlans(newRows)

    return NextResponse.json({
      success: true,
      mode,
      channelId,
      trendSource: ranking?.source ?? "fallback",
      daysProcessed: targetDates.length,
      slotsCreated: newRows.length,
      dates: targetDates,
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
