import { proxyJson } from "@/lib/proxy"

// 음원 라이브러리 장르별 적립 현황(#48) — FastAPI /api/music/library/stats.
export const dynamic = "force-dynamic"

export async function GET() {
  return proxyJson("/api/music/library/stats", { method: "GET" })
}
