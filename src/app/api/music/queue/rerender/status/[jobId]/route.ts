import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// #33 재렌더 상태 폴링 — FastAPI GET /music/queue/rerender/status/{jobId}.
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params
  return proxyJson(`/music/queue/rerender/status/${encodeURIComponent(jobId)}`, { method: "GET" })
}
