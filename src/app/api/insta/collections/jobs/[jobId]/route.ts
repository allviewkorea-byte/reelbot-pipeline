import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// GET /api/insta/collections/jobs/{jobId} — 컬렉션 릴스 진행 상태.
export const dynamic = "force-dynamic"

export async function GET(_req: NextRequest, { params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params
  return proxyJson(`/insta/collections/jobs/${encodeURIComponent(jobId)}`, { method: "GET" })
}
