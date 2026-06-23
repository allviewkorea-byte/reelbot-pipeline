import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 특정 작업 상세(#36) — FastAPI /api/music/jobs/{jobId}.
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params
  return proxyJson(`/api/music/jobs/${encodeURIComponent(jobId)}`, { method: "GET" })
}
