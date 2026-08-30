import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 검토 대기(pending) 음악 영상 큐 — FastAPI /music/queue 로 프록시.
// channel(운동 채널 2단계): 미지정이면 백엔드가 where 로 해석한다.
export const dynamic = "force-dynamic"

export async function GET(request: NextRequest) {
  const channel = request.nextUrl.searchParams.get("channel")
  const qs = channel ? `?channel=${encodeURIComponent(channel)}` : ""
  return proxyJson(`/music/queue${qs}`, { method: "GET" })
}
