import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 영상별 PLAY LIST 표시 토글(#39) → FastAPI POST /music/queue/{mixId}/show-playlist.
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ mixId: string }> },
) {
  const { mixId } = await params
  const body = await request.json().catch(() => ({}))
  return proxyJson(`/music/queue/${encodeURIComponent(mixId)}/show-playlist`, { method: "POST", body })
}
