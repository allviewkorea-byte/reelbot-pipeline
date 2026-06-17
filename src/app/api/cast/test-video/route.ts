import { NextRequest, NextResponse } from "next/server"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"
import { getLatestTestVideo, saveLatestTestVideo } from "@/lib/supabase"

// /cast 테스트 영상 최신 1건 — 채널당 영속(이탈/복귀해도 패널 유지).
//  GET  ?channelId= → { video_url, youtube_url, job_id, created_at } | null
//  POST { video_url, youtube_url, job_id } → 최신으로 upsert(channel_id PK)
// 비밀 키는 서버사이드(Supabase admin). 테이블 미존재/오류엔 안전 기본값(null)로 방어.
export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  const channelId = req.nextUrl.searchParams.get("channelId") || BAEKGOM_CHANNEL_ID
  const row = await getLatestTestVideo(channelId)
  return NextResponse.json({ success: true, video: row })
}

export async function POST(req: NextRequest) {
  let channelId = BAEKGOM_CHANNEL_ID
  let video_url: string | null = null
  let youtube_url: string | null = null
  let job_id: string | null = null
  try {
    const body = await req.json()
    if (typeof body?.channelId === "string" && body.channelId) channelId = body.channelId
    if (typeof body?.video_url === "string") video_url = body.video_url
    if (typeof body?.youtube_url === "string") youtube_url = body.youtube_url
    if (typeof body?.job_id === "string") job_id = body.job_id
  } catch {
    return NextResponse.json({ success: false, error: "Invalid JSON" }, { status: 400 })
  }
  if (!video_url && !youtube_url) {
    return NextResponse.json({ success: false, error: "video_url 또는 youtube_url 이 필요합니다" }, { status: 400 })
  }

  try {
    await saveLatestTestVideo({ channelId, video_url, youtube_url, job_id })
    return NextResponse.json({ success: true })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "알 수 없는 오류"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
