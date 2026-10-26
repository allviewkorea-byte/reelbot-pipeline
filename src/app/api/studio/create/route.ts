import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/studio/create { name, description } — AI 가 bible 작성 → 캐릭터 등록 → 얼굴 후보 4장 생성 시작.
export const dynamic = "force-dynamic"
export const maxDuration = 60

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}))
  return proxyJson("/studio/create", { method: "POST", body, timeoutMs: 55_000 })
}
