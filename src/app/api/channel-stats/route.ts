import { NextResponse } from "next/server"

// 백곰 채널 통계(서버 전용) — YouTube Data API v3 channels.statistics 1콜.
// YOUTUBE_API_KEY 는 서버에서만 사용(NEXT_PUBLIC_ 금지). 키/채널ID 미설정·실패 시
// 더미 금지 → 모든 값 null + error:true. 통계는 자주 안 변해 1시간 캐시.
const YT_BASE = "https://www.googleapis.com/youtube/v3"

interface ChannelStats {
  subscriberCount: number | null
  viewCount: number | null
  videoCount: number | null
  averageViews: number | null
  error?: boolean
}

const EMPTY: ChannelStats = {
  subscriberCount: null,
  viewCount: null,
  videoCount: null,
  averageViews: null,
  error: true,
}

const num = (v: unknown): number | null => {
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

export async function GET() {
  const key = (process.env.YOUTUBE_API_KEY || "").trim()
  const channelId = (process.env.YOUTUBE_CHANNEL_ID || "").trim()
  if (!key || !channelId) {
    return NextResponse.json(EMPTY) // 미설정 → 더미 없이 null
  }
  try {
    const url = new URL(`${YT_BASE}/channels`)
    url.searchParams.set("part", "statistics")
    url.searchParams.set("id", channelId)
    url.searchParams.set("key", key)
    const res = await fetch(url.toString(), { next: { revalidate: 3600 } }) // 1시간 캐시
    if (!res.ok) return NextResponse.json(EMPTY)
    const data = await res.json()
    const s = data?.items?.[0]?.statistics
    if (!s) return NextResponse.json(EMPTY)

    const subscriberCount = s.hiddenSubscriberCount ? null : num(s.subscriberCount)
    const viewCount = num(s.viewCount)
    const videoCount = num(s.videoCount)
    const averageViews =
      viewCount != null && videoCount != null && videoCount > 0
        ? Math.round(viewCount / videoCount)
        : null

    return NextResponse.json({ subscriberCount, viewCount, videoCount, averageViews })
  } catch {
    return NextResponse.json(EMPTY)
  }
}
