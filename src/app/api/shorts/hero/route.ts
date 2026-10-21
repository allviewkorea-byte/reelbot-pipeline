import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// GET /api/shorts/hero?channel= — hero 준비 상태·콘셉트·최근 실행(미리보기·비용·관련 동영상)·곡 분석·앤섬 상태.
export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  const channel = req.nextUrl.searchParams.get("channel") || "workout_music"
  return proxyJson(`/shorts/hero?channel=${encodeURIComponent(channel)}`, { method: "GET" })
}
