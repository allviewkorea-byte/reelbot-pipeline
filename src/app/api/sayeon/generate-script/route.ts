import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"
import { TIMEOUT } from "@/lib/api-timeout"

// 자동 사연 작성(gpt-4o-mini 1회). 동기지만 LLM 생성이라 HEAVY timeout 적용.
export async function POST(request: NextRequest) {
  const body = await request.json()
  return proxyJson("/sayeon/generate-script", {
    method: "POST",
    body,
    timeoutMs: TIMEOUT.HEAVY,
  })
}
