import { proxyJson } from "@/lib/proxy"

// 가이드 페이지: 장르 팔레트 + 최근 주제 10개 — FastAPI /music/themes 로 프록시.
export async function GET() {
  return proxyJson("/music/themes", { method: "GET" })
}
