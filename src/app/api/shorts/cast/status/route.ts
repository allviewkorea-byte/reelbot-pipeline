import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// GET /api/shorts/cast/status?channel=&role= — 전체 생성 진행상태(idle|running|done|failed).
export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams
  const qs = new URLSearchParams({ channel: p.get("channel") || "workout_music", role: p.get("role") || "lead" })
  return proxyJson(`/shorts/cast/status?${qs}`, { method: "GET" })
}
