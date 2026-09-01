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
  const res = await proxyJson(`/api/music/genre-prompt?${qs}`, { method: "GET" })
  // 클릭마다 새 프롬프트여야 하므로 어떤 계층에도 캐시되면 안 된다.
  // (실측상 지금도 캐시되진 않지만 응답에 Cache-Control 이 아예 없어서 브라우저·
  //  프록시 변수가 남아 있었다. proxyJson 은 다른 라우트도 쓰므로 여기서만 붙인다.)
  res.headers.set("Cache-Control", "no-store, max-age=0")
  return res
}
