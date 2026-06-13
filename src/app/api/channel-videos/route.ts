import { NextResponse } from "next/server"
import { fetchChannelUploads } from "@/lib/youtube"

// 쿼터 절약 — 15분 캐시(ISR). 채널 공개 영상이 자주 바뀌지 않으므로 충분.
export const revalidate = 900

// GET /api/channel-videos — 백곰 채널의 '공개' 업로드 영상(MarqueeVideo[]).
// YOUTUBE_CHANNEL_ID / YOUTUBE_API_KEY 는 서버 전용(NEXT_PUBLIC 아님) — 키 미노출.
// 미설정·에러·쿼터 초과 시 빈 배열 반환 → 마퀴가 더미로 폴백.
export async function GET() {
  const channelId = (process.env.YOUTUBE_CHANNEL_ID || "").trim()
  if (!channelId) {
    console.warn("[channel-videos] YOUTUBE_CHANNEL_ID 미설정 — 빈 배열 반환")
    return NextResponse.json({ videos: [] })
  }
  try {
    const videos = await fetchChannelUploads(channelId, 12)
    return NextResponse.json({ videos })
  } catch (e) {
    console.warn(
      "[channel-videos] 조회 실패 — 빈 배열 폴백:",
      e instanceof Error ? e.message : e,
    )
    return NextResponse.json({ videos: [] })
  }
}
