import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 음악 채널 유튜브 연동 여부(운동 채널 3단계) — FastAPI /api/music/youtube/status 프록시.
// channel 미지정이면 백엔드가 where 로 해석한다(기존 응답과 동일).
export const dynamic = "force-dynamic"

export async function GET(request: NextRequest) {
  const channel = request.nextUrl.searchParams.get("channel")
  const qs = channel ? `?channel=${encodeURIComponent(channel)}` : ""
  return proxyJson(`/api/music/youtube/status${qs}`, { method: "GET" })
}
