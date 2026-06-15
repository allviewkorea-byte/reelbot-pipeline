import { NextRequest, NextResponse } from "next/server"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"
import { generateCalendar, type GenerateMode } from "@/lib/calendar-run"
import { isAuthorizedCron } from "@/lib/cron-auth"

// 캘린더 롤링 자동 생성(7b): 트렌드 근거로 하루 3슬롯 컨셉 자동 배정 → content_plans 저장.
//  - mode=fill30: 오늘~+29일(30일) 초기 채우기
//  - mode=rollOne: +30일(그 1일치) 롤링
// 멱등: 이미 있는(수동 포함) 슬롯은 보존, 빈 슬롯만 채움.
// 보안(7c): DB 쓰기라 CRON_SECRET 으로 보호 — Authorization: Bearer ${CRON_SECRET} 필요.
//   (수동 fill30 실행 시에도 이 헤더 첨부. 자동 롤링은 /api/cron/roll 사용.)
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest) {
  if (!isAuthorizedCron(req)) {
    return NextResponse.json({ success: false, error: "unauthorized" }, { status: 401 })
  }

  let body: { mode?: string; channelId?: string }
  try {
    body = await req.json()
  } catch {
    body = {}
  }
  const mode: GenerateMode = body.mode === "rollOne" ? "rollOne" : "fill30"
  const channelId = body.channelId || BAEKGOM_CHANNEL_ID

  try {
    const result = await generateCalendar(mode, channelId)
    return NextResponse.json({ success: true, ...result })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
