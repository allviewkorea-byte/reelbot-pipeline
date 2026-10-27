import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// GET /api/insta/coordi/jobs/{jobId} — 코디 진행 상태(채울 종류 → 쿠팡 고르기 → 입히기).
export const dynamic = "force-dynamic"

export async function GET(_req: NextRequest, { params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params
  return proxyJson(`/insta/coordi/jobs/${encodeURIComponent(jobId)}`, { method: "GET" })
}
