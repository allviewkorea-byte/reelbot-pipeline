import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 1곡 풀 테스트 상태 폴링(#25) — FastAPI /api/music/test-render-full/status/{jobId}.
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params
  return proxyJson(`/api/music/test-render-full/status/${encodeURIComponent(jobId)}`, { method: "GET" })
}
