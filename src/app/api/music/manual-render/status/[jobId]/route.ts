import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 수동 영상 생성 상태 폴링(#26) — FastAPI /api/music/manual-render/status/{jobId}.
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params
  return proxyJson(`/api/music/manual-render/status/${encodeURIComponent(jobId)}`, { method: "GET" })
}
