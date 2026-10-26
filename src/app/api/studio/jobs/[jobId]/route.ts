import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// GET /api/studio/jobs/{jobId} — 이미지 생성 작업 진행(total/done/failed/errors/cost).
export const dynamic = "force-dynamic"

export async function GET(_req: NextRequest, { params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params
  return proxyJson(`/studio/jobs/${encodeURIComponent(jobId)}`, { method: "GET" })
}
