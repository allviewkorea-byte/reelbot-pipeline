import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params
  return proxyJson(`/jobs/${encodeURIComponent(jobId)}/status`, { method: "GET" })
}
