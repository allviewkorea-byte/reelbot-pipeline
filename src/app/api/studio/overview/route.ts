import { proxyJson } from "@/lib/proxy"

// GET /api/studio/overview — 스튜디오 첫 화면: 채널별 캐릭터(얼굴 썸네일·준비 상태).
export const dynamic = "force-dynamic"

export async function GET() {
  return proxyJson("/studio/overview", { method: "GET" })
}
