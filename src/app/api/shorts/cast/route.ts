import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// GET /api/shorts/cast?channel= — 쇼츠 사람 캐스트(아스펙트 URL·확정 상태). 백곰 /api/cast 와 분리.
export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  const channel = req.nextUrl.searchParams.get("channel") || "workout_music"
  return proxyJson(`/shorts/cast?channel=${encodeURIComponent(channel)}`, { method: "GET" })
}
