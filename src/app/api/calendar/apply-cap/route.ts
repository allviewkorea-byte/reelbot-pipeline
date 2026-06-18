import { NextRequest, NextResponse } from "next/server"
import { BAEKGOM_CHANNEL_ID, clampDailyCap } from "@/lib/content-plan"
import { applyCapToFuture } from "@/lib/calendar-run"

// POST /api/calendar/apply-cap { cap } — daily_cap 변경 시 오늘 이후 미제작 날짜만
// 새 cap 개수로 캘린더 재생성(과거·제작완료 보존). DB 만 사용 → Hobby 안전.
export const dynamic = "force-dynamic"
export const maxDuration = 60

export async function POST(req: NextRequest) {
  let cap = 0
  let channelId = BAEKGOM_CHANNEL_ID
  try {
    const body = await req.json()
    cap = clampDailyCap(body?.cap)
    if (typeof body?.channelId === "string" && body.channelId) channelId = body.channelId
  } catch {
    return NextResponse.json({ success: false, error: "Invalid JSON" }, { status: 400 })
  }
  try {
    const result = await applyCapToFuture(channelId, cap)
    return NextResponse.json({ success: true, cap, ...result })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
