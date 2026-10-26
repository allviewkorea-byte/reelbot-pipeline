import { proxyJson } from "@/lib/proxy"

// GET /api/insta/usage — 외부 API 오늘 사용량(유튜브 유닛·상한, 키 연결 여부).
export const dynamic = "force-dynamic"

export async function GET() {
  return proxyJson("/insta/usage", { method: "GET" })
}
