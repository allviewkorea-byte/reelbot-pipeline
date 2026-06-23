import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 실패 카드 [닫기](#36) — active 목록에서 제거(상태 failed 보존).
export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params
  return proxyJson(`/api/music/jobs/${encodeURIComponent(jobId)}/dismiss`, { method: "POST" })
}
