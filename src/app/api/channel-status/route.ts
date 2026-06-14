import { NextRequest, NextResponse } from "next/server"
import { getChannelStatus, setChannelStatus } from "@/lib/supabase"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"

// GET /api/channel-status?channelId= → { isActive }. 미존재/에러/env 미설정 → false(방어).
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const channelId = searchParams.get("channelId") || BAEKGOM_CHANNEL_ID
  const isActive = await getChannelStatus(channelId)
  return NextResponse.json({ success: true, channelId, isActive })
}

// POST { channelId, isActive } → 저장 후 반환. content-plans route 와 동일 패턴.
export async function POST(req: NextRequest) {
  let body: { channelId?: string; isActive?: boolean }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ success: false, error: "Invalid JSON" }, { status: 400 })
  }
  if (typeof body?.isActive !== "boolean") {
    return NextResponse.json(
      { success: false, error: "isActive(boolean) 는 필수입니다" },
      { status: 400 },
    )
  }
  const channelId = body.channelId || BAEKGOM_CHANNEL_ID
  try {
    await setChannelStatus(channelId, body.isActive)
    return NextResponse.json({ success: true, channelId, isActive: body.isActive })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
