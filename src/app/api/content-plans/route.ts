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
  // id: 유효한 UUID 로 생성(텍스트/uuid 컬럼 모두 호환). created_at 은 보내지 않고
  // DB default(now())에 맡긴다 — 정상 동작하는 channels 저장 패턴과 동일하게.
  const plan: ContentPlan = {
    id: body.id || crypto.randomUUID(),
    channel_id: body.channel_id || BAEKGOM_CHANNEL_ID,
    date: body.date,
    concept: body.concept,
    title: body.title ?? null,
    status: body.status || "planned",
    memo: body.memo ?? null,
  }
  try {
    await upsertContentPlan(plan)
    return NextResponse.json({ success: true, plan })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
