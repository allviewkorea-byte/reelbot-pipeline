import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"
import { TIMEOUT } from "@/lib/api-timeout"

// 콘티 생성은 gpt-image-1 다중 호출로 1~3분 걸리므로 HEAVY(5분) timeout 적용.
export async function POST(request: NextRequest) {
  const body = await request.json()
  return proxyJson("/storyboard/generate", { method: "POST", body, timeoutMs: TIMEOUT.HEAVY })
}
