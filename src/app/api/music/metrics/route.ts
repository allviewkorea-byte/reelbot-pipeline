import { NextRequest, NextResponse } from "next/server"
import { DEFAULT_MUSIC_CHANNEL, WORKOUT_CHANNEL_ID, resolveMusicChannel } from "@/lib/music"

// 음악 채널 통계 — YouTube Data API v3 channels.statistics 1콜.
// 백곰 /api/channel-stats 패턴 동일(서버 전용 YOUTUBE_API_KEY + 채널별 채널 ID).
// 미설정·실패 시 더미 금지 → 모든 값 null. 통계는 자주 안 변해 1시간 캐시.
//
// 채널별 env(운동 채널 3단계): where→YOUTUBE_CHANNEL_ID_MUSIC / 운동→YOUTUBE_CHANNEL_ID_WORKOUT.
// **기존 키 이름은 바꾸지 않는다** — where 가 즉시 깨진다.
const YT_BASE = "https://www.googleapis.com/youtube/v3"

const CHANNEL_ENV: Record<string, string> = {
  [DEFAULT_MUSIC_CHANNEL]: "YOUTUBE_CHANNEL_ID_MUSIC",
  [WORKOUT_CHANNEL_ID]: "YOUTUBE_CHANNEL_ID_WORKOUT",
}

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

export async function GET(request: NextRequest) {
  const channel = resolveMusicChannel(request.nextUrl.searchParams.get("channel"))
  const key = (process.env.YOUTUBE_API_KEY || "").trim()
  const channelId = (process.env[CHANNEL_ENV[channel]] || "").trim()
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
