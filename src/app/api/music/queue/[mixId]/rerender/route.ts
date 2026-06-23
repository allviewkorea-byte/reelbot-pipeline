import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// #33 수동 재렌더 시작 — FastAPI POST /music/queue/{mixId}/rerender (비동기 job_id 반환).
export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ mixId: string }> },
) {
  const { mixId } = await params
  return proxyJson(`/music/queue/${encodeURIComponent(mixId)}/rerender`, { method: "POST" })
}
