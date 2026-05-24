import { NextRequest, NextResponse } from "next/server"
import { upsertChannel, deleteChannelRow } from "@/lib/supabase"
import type { Channel } from "@/lib/channels"

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ channelId: string }> },
) {
  const { channelId } = await params
  let channel: Channel
  try {
    channel = await req.json()
  } catch {
    return NextResponse.json({ success: false, error: "Invalid JSON" }, { status: 400 })
  }
  if (!channel?.id || channel.id !== channelId) {
    return NextResponse.json(
      { success: false, error: "본문 채널 id가 경로와 일치하지 않습니다" },
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

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ channelId: string }> },
) {
  const { channelId } = await params
  try {
    await deleteChannelRow(channelId)
    return NextResponse.json({ success: true })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
