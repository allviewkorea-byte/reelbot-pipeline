import { NextRequest, NextResponse } from "next/server"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"
import { generateCalendar } from "@/lib/calendar-run"
import { isAuthorizedCron } from "@/lib/cron-auth"

// 7c: 캘린더 롤링(+30일 1일치). finalize 로 갱신된 trend_rankings 를 읽어 생성.
// DB 만 사용(외부 API 없음) → Hobby 10초 안전. 멱등(빈 슬롯만 채움).
export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  if (!isAuthorizedCron(req)) {
    return NextResponse.json({ success: false, error: "unauthorized" }, { status: 401 })
  }
  try {
    const result = await generateCalendar("rollOne", BAEKGOM_CHANNEL_ID)
    return NextResponse.json({ success: true, ...result })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
