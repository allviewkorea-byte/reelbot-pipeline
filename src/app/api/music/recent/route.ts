import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 최근 업로드된 음악 영상(공개 완료) — FastAPI /music/recent 로 프록시(대시보드 마퀴용).
// channel: 미지정이면 쿼리를 붙이지 않고 백엔드가 where 로 해석한다(기존 동작 동일).
export const dynamic = "force-dynamic"

export async function GET(request: NextRequest) {
  const channel = request.nextUrl.searchParams.get("channel")
  const qs = channel ? `?channel=${encodeURIComponent(channel)}` : ""
  return proxyJson(`/music/recent${qs}`, { method: "GET" })
}
