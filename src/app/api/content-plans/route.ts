import { NextRequest, NextResponse } from "next/server"
import { listContentPlans, upsertContentPlan } from "@/lib/supabase"
import { BAEKGOM_CHANNEL_ID, type ContentPlan } from "@/lib/content-plan"

// GET /api/content-plans?channel=&from=YYYY-MM-DD&to=YYYY-MM-DD — 기간 조회.
// 테이블 미존재/에러 시에도 빈 배열(listContentPlans 방어) → 캘린더 안 깨짐.
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const channel = searchParams.get("channel") || BAEKGOM_CHANNEL_ID
  const from = searchParams.get("from") || undefined
  const to = searchParams.get("to") || undefined
  const plans = await listContentPlans(channel, from, to)
  return NextResponse.json({ success: true, plans })
}

// POST /api/content-plans — 콘텐츠 플랜 생성/수정(upsert). id 없으면 생성.
export async function POST(req: NextRequest) {
  let body: Partial<ContentPlan>
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ success: false, error: "Invalid JSON" }, { status: 400 })
  }
  if (!body?.date || !body?.concept) {
    return NextResponse.json(
      { success: false, error: "date / concept 은 필수입니다" },
      { status: 400 },
    )
  }
  const plan: ContentPlan = {
    id: body.id || `cp_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    channel_id: body.channel_id || BAEKGOM_CHANNEL_ID,
    date: body.date,
    concept: body.concept,
    title: body.title ?? null,
    status: body.status || "planned",
    memo: body.memo ?? null,
    created_at: body.created_at || new Date().toISOString(),
  }
  try {
    await upsertContentPlan(plan)
    return NextResponse.json({ success: true, plan })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
