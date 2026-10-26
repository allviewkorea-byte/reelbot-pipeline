import { proxyJson } from "@/lib/proxy"

// GET /api/studio/characters — 캐릭터 스튜디오 캐릭터 목록(백엔드 /studio/characters).
export const dynamic = "force-dynamic"

export async function GET() {
  return proxyJson("/studio/characters", { method: "GET" })
}
