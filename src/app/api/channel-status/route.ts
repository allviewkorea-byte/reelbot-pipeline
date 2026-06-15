import { NextRequest, NextResponse } from "next/server"
import { getChannelStatus, setChannelStatus } from "@/lib/supabase"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"
import type { ChannelMode } from "@/lib/channel-status"

// GET /api/channel-status?channelId= → { isActive, mode }. 미존재/에러 → { false, "semi" } 방어.
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const channelId = searchParams.get("channelId") || BAEKGOM_CHANNEL_ID
  const { isActive, mode } = await getChannelStatus(channelId)
  return NextResponse.json({ success: true, channelId, isActive, mode })
}

// POST { channelId, isActive?, mode? } → 제공된 것만 저장 후 반환. (가동 토글·모드 토글 공용)
export async function POST(req: NextRequest) {
  let body: { channelId?: string; isActive?: boolean; mode?: string }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ success: false, error: "Invalid JSON" }, { status: 400 })
  }
  const hasActive = typeof body?.isActive === "boolean"
  const hasMode = body?.mode === "auto" || body?.mode === "semi"
  if (!hasActive && !hasMode) {
    return NextResponse.json(
      { success: false, error: "isActive(boolean) 또는 mode('auto'|'semi') 중 하나는 필요합니다" },
      { status: 400 },
    )
  }
  const channelId = body.channelId || BAEKGOM_CHANNEL_ID
  const patch: { isActive?: boolean; mode?: ChannelMode } = {}
  if (hasActive) patch.isActive = body.isActive
  if (hasMode) patch.mode = body.mode as ChannelMode
  try {
    await setChannelStatus(channelId, patch)
    const { isActive, mode } = await getChannelStatus(channelId)
    return NextResponse.json({ success: true, channelId, isActive, mode })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
