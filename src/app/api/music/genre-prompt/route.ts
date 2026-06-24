import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 장르별 이미지 프롬프트 1개(#49) — FastAPI /api/music/genre-prompt 로 프록시.
// 클릭마다 호출돼 같은 장르라도 풀(15개)에서 다른 프롬프트를 받는다.
export const dynamic = "force-dynamic"

export async function GET(request: NextRequest) {
  const genre = request.nextUrl.searchParams.get("genre") || ""
  return proxyJson(`/api/music/genre-prompt?genre=${encodeURIComponent(genre)}`, { method: "GET" })
}
