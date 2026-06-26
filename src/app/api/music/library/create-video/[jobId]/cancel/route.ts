import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params
  return proxyJson(`/api/music/library/create-video/${encodeURIComponent(jobId)}/cancel`, { method: "POST" })
}
