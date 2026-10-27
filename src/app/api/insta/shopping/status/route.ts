import { proxyJson } from "@/lib/proxy"

// GET /api/insta/shopping/status — 쿠팡·네이버 연결 여부 + 오늘 호출 수.
export const dynamic = "force-dynamic"

export async function GET() {
  return proxyJson("/insta/shopping/status", { method: "GET" })
}
