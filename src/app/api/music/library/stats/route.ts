import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 음원 라이브러리 장르별 적립 현황(#48) — FastAPI /api/music/library/stats.
// channel(운동 채널 2단계): 미지정이면 백엔드가 where 로 해석한다.
export const dynamic = "force-dynamic"

export async function GET(request: NextRequest) {
  const channel = request.nextUrl.searchParams.get("channel")
  const qs = channel ? `?channel=${encodeURIComponent(channel)}` : ""
  return proxyJson(`/api/music/library/stats${qs}`, { method: "GET" })
}
