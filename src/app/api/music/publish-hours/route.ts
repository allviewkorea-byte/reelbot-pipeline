import { NextRequest, NextResponse } from "next/server"
import { getMusicPublishHours, setMusicPublishHours } from "@/lib/supabase"
import { AUTO_RUN_CHANNELS } from "@/lib/music"

// 음악 자동 회차 공개 시각(PR-2a) — channel_status.channel_config.publish_hours(jsonb, 신규 컬럼 없음).
// GET ?channelId= → { success, channelId, hours }. POST { channelId, hours: number[] } → 저장 후 반환.
// 자동 회차 대상 채널(AUTO_RUN_CHANNELS: 운동·where)만 받는다.
export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  const channelId = new URL(req.url).searchParams.get("channelId") || ""
  if (!AUTO_RUN_CHANNELS.includes(channelId)) {
    return NextResponse.json({ success: false, error: "자동 회차 대상 채널이 아닙니다" }, { status: 400 })
  }
  return NextResponse.json({ success: true, channelId, hours: await getMusicPublishHours(channelId) })
}

export async function POST(req: NextRequest) {
  let body: { channelId?: string; hours?: unknown }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ success: false, error: "Invalid JSON" }, { status: 400 })
  }
  const channelId = body.channelId || ""
  if (!AUTO_RUN_CHANNELS.includes(channelId)) {
    return NextResponse.json({ success: false, error: "자동 회차 대상 채널이 아닙니다" }, { status: 400 })
  }
  if (!Array.isArray(body.hours) || body.hours.length === 0) {
    return NextResponse.json({ success: false, error: "hours 배열이 필요합니다" }, { status: 400 })
  }
  try {
    const hours = await setMusicPublishHours(channelId, body.hours as number[])
    return NextResponse.json({ success: true, channelId, hours })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
