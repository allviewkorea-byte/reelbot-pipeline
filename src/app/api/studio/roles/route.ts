import { proxyJson } from "@/lib/proxy"

// GET /api/studio/roles — 캐릭터 스튜디오 역할 분류·필수 역할·이름 규칙(백엔드 /studio/roles).
export const dynamic = "force-dynamic"

export async function GET() {
  return proxyJson("/studio/roles", { method: "GET" })
}
