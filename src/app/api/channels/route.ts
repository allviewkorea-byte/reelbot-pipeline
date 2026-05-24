import { NextRequest, NextResponse } from "next/server"
import { listChannels, upsertChannel } from "@/lib/supabase"
import type { Channel } from "@/lib/channels"

export async function GET() {
  try {
    const channels = await listChannels()
    return NextResponse.json({ success: true, channels })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}

export async function POST(req: NextRequest) {
  let channel: Channel
  try {
    channel = await req.json()
  } catch {
    return NextResponse.json({ success: false, error: "Invalid JSON" }, { status: 400 })
  }
  if (!channel?.id || !channel?.name || !channel?.platform) {
    return NextResponse.json(
      { success: false, error: "id / name / platform 은 필수입니다" },
      { status: 400 },
    )
  }
  try {
    await upsertChannel(channel)
    return NextResponse.json({ success: true, channel })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
