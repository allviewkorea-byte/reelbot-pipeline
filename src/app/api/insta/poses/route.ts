import { proxyJson } from "@/lib/proxy"
import { TIMEOUT } from "@/lib/api-timeout"

// GET /api/insta/poses — 포즈 라이브러리(카테고리·포즈·설정). 첫 호출은 목록을 받아 오느라 조금 걸린다.
export const dynamic = "force-dynamic"

export async function GET() {
  return proxyJson("/insta/poses", { method: "GET", timeoutMs: TIMEOUT.QUICK * 2 })
}
