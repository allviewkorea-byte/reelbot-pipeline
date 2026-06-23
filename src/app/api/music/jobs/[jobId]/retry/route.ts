import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"
import { TIMEOUT } from "@/lib/api-timeout"

// 실패 카드 [재시도](#36) — 같은 종류 작업 재시작(manual/rerender). 백그라운드 트리거.
export const maxDuration = 60

export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params
  return proxyJson(`/api/music/jobs/${encodeURIComponent(jobId)}/retry`, {
    method: "POST",
    timeoutMs: TIMEOUT.QUICK,
  })
}
