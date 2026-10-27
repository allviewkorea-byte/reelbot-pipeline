import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// GET /api/insta/looks/jobs/{jobId} — 상품 고르기 진행 상태.
export const dynamic = "force-dynamic"

export async function GET(_req: NextRequest, { params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params
  return proxyJson(`/insta/looks/jobs/${encodeURIComponent(jobId)}`, { method: "GET" })
}
