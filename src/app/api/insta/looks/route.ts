import { proxyJson } from "@/lib/proxy"

// GET /api/insta/looks — 최근 코디(룩별 고른 상품·예비 후보).
export const dynamic = "force-dynamic"

export async function GET() {
  return proxyJson("/insta/looks?limit=10", { method: "GET" })
}
