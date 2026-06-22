import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"
import { TIMEOUT } from "@/lib/api-timeout"

// 유튜브 공개 업로드(썸네일 게이트는 백엔드에서 400) → FastAPI /music/queue/{mixId}/publish.
export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ mixId: string }> },
) {
  const { mixId } = await params
  return proxyJson(`/music/queue/${encodeURIComponent(mixId)}/publish`, {
    method: "POST",
    timeoutMs: TIMEOUT.VERY_HEAVY, // 영상 다운로드 + 유튜브 업로드(수 분)
  })
}
