import { NextRequest, NextResponse } from "next/server"
import { resolveChannelId, fetchChannelVideoStats } from "@/lib/youtube"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"
import { saveChannelVideos } from "@/lib/supabase"
import { isAuthorizedCron } from "@/lib/cron-auth"
import { TREND_SOURCE_CHANNELS, TREND_PER_CHANNEL_MAX, todayKST } from "@/lib/trend-concepts"

// 7c: 대상 사연 채널 1개만(index=N) 수집해 trend_channel_videos 에 부분저장.
// 각 호출 = 1채널(~4 unit, 수 초) → Hobby 10초 안전. 멱등(같은 date_index 덮어씀).
export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  if (!isAuthorizedCron(req)) {
    return NextResponse.json({ success: false, error: "unauthorized" }, { status: 401 })
  }

  const total = TREND_SOURCE_CHANNELS.length
  const { searchParams } = new URL(req.url)
  const index = Number(searchParams.get("index"))
  if (!Number.isInteger(index) || index < 0 || index >= total) {
    return NextResponse.json(
      { success: false, error: `index 는 0~${total - 1} 사이 정수여야 합니다`, total },
      { status: 400 },
    )
  }

  const ref = TREND_SOURCE_CHANNELS[index]
  const date = todayKST()
  const channelId = BAEKGOM_CHANNEL_ID

  try {
    const id = await resolveChannelId(ref)
    if (!id) {
      // 변환 실패 → 빈 부분결과 저장(finalize 가 그냥 건너뜀). 전체 안 깨짐.
      await saveChannelVideos({ id: `${date}_${index}`, channel_id: channelId, date, source_ref: ref, videos: [] })
      return NextResponse.json({ success: true, index, total, ref, saved: 0, note: "채널 ID 변환 실패" })
    }
    const vids = await fetchChannelVideoStats(id, TREND_PER_CHANNEL_MAX)
    const videos = vids.map((v) => ({ title: v.title, viewCount: v.viewCount, publishedAt: v.publishedAt }))
    await saveChannelVideos({ id: `${date}_${index}`, channel_id: channelId, date, source_ref: ref, videos })
    return NextResponse.json({ success: true, index, total, ref, saved: videos.length })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, index, total, ref, error: msg }, { status: 500 })
  }
}
