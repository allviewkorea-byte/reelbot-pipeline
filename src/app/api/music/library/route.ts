import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 음원 라이브러리 목록(#48) — FastAPI /api/music/library 로 프록시(쿼리 그대로 전달).
export const dynamic = "force-dynamic"

export async function GET(request: NextRequest) {
  const qs = request.nextUrl.search // ?genre=&used=&limit=&offset=
  return proxyJson(`/api/music/library${qs}`, { method: "GET" })
}
