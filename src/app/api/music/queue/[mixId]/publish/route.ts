import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"
import { TIMEOUT } from "@/lib/api-timeout"
import { getChannelStatus } from "@/lib/supabase"
import { MUSIC_CHANNEL_ID } from "@/lib/music"

// 유튜브 공개 업로드(썸네일 게이트는 백엔드에서 400) → FastAPI /music/queue/{mixId}/publish.
//
// AI 표시(containsSyntheticMedia)는 대시보드 토글(channel_status.synthetic_media)에서
// 결정된다. 백엔드는 이 값을 알 수 없으므로 사연 채널(api/sayeon/generate)과 동일하게
// 여기(프록시)에서 주입한다. 이 주입이 없어 음악 영상에는 AI 표시가 한 번도 전달되지
// 않았다. 조회 실패 시엔 미주입 → 백엔드 YOUTUBE_SYNTHETIC_MEDIA env 폴백.
export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ mixId: string }> },
) {
  const { mixId } = await params
  const body: { synthetic_media?: boolean } = {}
  try {
    const { syntheticMedia } = await getChannelStatus(MUSIC_CHANNEL_ID)
    body.synthetic_media = syntheticMedia
  } catch {
    /* 조회 실패 → 미주입(백엔드 env 폴백) */
  }
  return proxyJson(`/music/queue/${encodeURIComponent(mixId)}/publish`, {
    method: "POST",
    body,
    timeoutMs: TIMEOUT.VERY_HEAVY, // 영상 다운로드 + 유튜브 업로드(수 분)
  })
}
