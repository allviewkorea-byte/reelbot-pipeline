import { proxyJson } from "@/lib/proxy"

// GET /api/insta/refs — 최근 유튜브 레퍼런스(썸네일·룩 분석) + 수집 상태.
export const dynamic = "force-dynamic"

export async function GET() {
  return proxyJson("/insta/refs?limit=20", { method: "GET" })
}
