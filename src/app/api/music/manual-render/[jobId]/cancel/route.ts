import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 수동 영상 생성 취소(#26-C) — FastAPI /api/music/manual-render/{jobId}/cancel.
// 현재 스텝 완료 후 검토 큐 적재 없이 종료(협조적 취소).
export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params
  return proxyJson(`/api/music/manual-render/${encodeURIComponent(jobId)}/cancel`, { method: "POST" })
}
