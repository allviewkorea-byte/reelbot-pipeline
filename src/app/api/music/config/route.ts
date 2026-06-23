import { NextRequest, NextResponse } from "next/server"
import { getMusicChannelConfig, setMusicChannelConfig } from "@/lib/supabase"
import { MUSIC_CHANNEL_ID, normalizeMusicConfig } from "@/lib/music"

// 음악 채널 설정(#37) — 슬로건·소셜·AI 명시(channel_status.channel_config jsonb).
// GET ?channelId= → { success, config }. POST { channelId?, config } → 저장 후 반환.
export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  const channelId = new URL(req.url).searchParams.get("channelId") || MUSIC_CHANNEL_ID
  const config = await getMusicChannelConfig(channelId)
  return NextResponse.json({ success: true, channelId, config })
}

export async function POST(req: NextRequest) {
  let body: { channelId?: string; config?: unknown }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ success: false, error: "Invalid JSON" }, { status: 400 })
  }
  const channelId = body.channelId || MUSIC_CHANNEL_ID
  const config = normalizeMusicConfig(body.config)
  try {
    await setMusicChannelConfig(channelId, config)
    return NextResponse.json({ success: true, channelId, config })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
