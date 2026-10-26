import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// GET /api/insta/outfit-jobs/{jobId} — 착장 작업 진행(단계·시도·비용).
export const dynamic = "force-dynamic"

export async function GET(_req: NextRequest, { params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params
  return proxyJson(`/insta/outfit-jobs/${encodeURIComponent(jobId)}`, { method: "GET" })
}
