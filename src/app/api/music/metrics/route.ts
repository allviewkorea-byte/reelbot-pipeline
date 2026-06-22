import { NextResponse } from "next/server"

// 음악 채널(Revezen) 통계 — YouTube Data API v3 channels.statistics 1콜.
// 백곰 /api/channel-stats 패턴 동일(서버 전용 YOUTUBE_API_KEY + 음악 채널 ID).
// 미설정·실패 시 더미 금지 → 모든 값 null. 통계는 자주 안 변해 1시간 캐시.
const YT_BASE = "https://www.googleapis.com/youtube/v3"

const EMPTY = {
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
  const channelId = (process.env.YOUTUBE_CHANNEL_ID_MUSIC || "").trim()
  if (!key || !channelId) {
    return NextResponse.json(EMPTY)
  }
  try {
    const url = new URL(`${YT_BASE}/channels`)
    url.searchParams.set("part", "statistics")
    url.searchParams.set("id", channelId)
    url.searchParams.set("key", key)
    const res = await fetch(url.toString(), { next: { revalidate: 3600 } })
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
