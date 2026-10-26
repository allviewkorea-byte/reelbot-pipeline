import { proxyJson } from "@/lib/proxy"

// GET /api/insta/outfit-options — 착장 선택 입력 풀(요일·컷·장소·포즈·아이웨어·상품 종류) + 예상 비용.
export const dynamic = "force-dynamic"

export async function GET() {
  return proxyJson("/insta/outfit-options", { method: "GET" })
}
