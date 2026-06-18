import { NextRequest, NextResponse } from "next/server"
import { getChannelStatus, setChannelStatus } from "@/lib/supabase"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"
import type { ChannelMode } from "@/lib/channel-status"

// GET /api/channel-status?channelId= → { isActive, mode, syntheticMedia, dailyCap }. 미존재/에러 → 안전 기본.
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const channelId = searchParams.get("channelId") || BAEKGOM_CHANNEL_ID
  const { isActive, mode, syntheticMedia, dailyCap } = await getChannelStatus(channelId)
  return NextResponse.json({ success: true, channelId, isActive, mode, syntheticMedia, dailyCap })
}

// POST { channelId, isActive?, mode?, syntheticMedia?, dailyCap? } → 제공된 것만 저장 후 반환.
// (가동 토글·공개/비공개 토글·AI 표시 토글·하루 생산 개수 공용)
export async function POST(req: NextRequest) {
  let body: { channelId?: string; isActive?: boolean; mode?: string; syntheticMedia?: boolean; dailyCap?: number }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ success: false, error: "Invalid JSON" }, { status: 400 })
  }
  const hasActive = typeof body?.isActive === "boolean"
  const hasMode = body?.mode === "auto" || body?.mode === "semi"
  const hasSynth = typeof body?.syntheticMedia === "boolean"
  const hasCap = typeof body?.dailyCap === "number"
  if (!hasActive && !hasMode && !hasSynth && !hasCap) {
    return NextResponse.json(
      { success: false, error: "isActive·mode·syntheticMedia·dailyCap 중 하나는 필요합니다" },
      { status: 400 },
    )
  }
  const channelId = body.channelId || BAEKGOM_CHANNEL_ID
  const patch: { isActive?: boolean; mode?: ChannelMode; syntheticMedia?: boolean; dailyCap?: number } = {}
  if (hasActive) patch.isActive = body.isActive
  if (hasMode) patch.mode = body.mode as ChannelMode
  if (hasSynth) patch.syntheticMedia = body.syntheticMedia
  if (hasCap) patch.dailyCap = body.dailyCap
  try {
    await setChannelStatus(channelId, patch)
    const { isActive, mode, syntheticMedia, dailyCap } = await getChannelStatus(channelId)
    return NextResponse.json({ success: true, channelId, isActive, mode, syntheticMedia, dailyCap })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
