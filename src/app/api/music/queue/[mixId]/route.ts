import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 큐 영상 삭제(#19) — FastAPI DELETE /music/queue/{mixId} 로 프록시.
// 단일 mix_id 한 행만 삭제(다른 영상 영향 0).
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ mixId: string }> },
) {
  const { mixId } = await params
  return proxyJson(`/music/queue/${encodeURIComponent(mixId)}`, { method: "DELETE" })
}
