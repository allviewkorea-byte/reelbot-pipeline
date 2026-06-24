import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 선택곡 영상 제작 상태 폴링(#48) — FastAPI /api/music/library/create-video/status/{jobId}.
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params
  return proxyJson(`/api/music/library/create-video/status/${encodeURIComponent(jobId)}`, {
    method: "GET",
  })
}
