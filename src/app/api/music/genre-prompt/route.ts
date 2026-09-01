import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 장르별 이미지 프롬프트 1개(#49) — FastAPI /api/music/genre-prompt 로 프록시.
// 클릭마다 호출돼 같은 장르라도 풀(15개)에서 다른 프롬프트를 받는다.
export const dynamic = "force-dynamic"

export async function GET(request: NextRequest) {
  const sp = request.nextUrl.searchParams
  // channel·action(5단계): 운동 채널은 장르 대신 action 으로 전용 풀에서 뽑는다.
  // 미지정이면 쿼리를 붙이지 않아 기존 요청 URL 과 문자 단위로 동일하다.
  const qs = ["genre", "channel", "action"]
    .map((k) => [k, (sp.get(k) || "").trim()] as const)
    .filter(([k, v]) => v || k === "genre")
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
    .join("&")
  return proxyJson(`/api/music/genre-prompt?${qs}`, { method: "GET" })
}
