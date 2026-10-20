import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// GET /api/shorts/series?channel= — 시즌 1 회차 계획·진행(series.json) + 테스트 제작 상태 + 미확정 캐스트.
export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  const channel = req.nextUrl.searchParams.get("channel") || "workout_music"
  return proxyJson(`/shorts/series?channel=${encodeURIComponent(channel)}`, { method: "GET" })
}
