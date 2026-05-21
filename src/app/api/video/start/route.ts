import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"
import { TIMEOUT } from "@/lib/api-timeout"

// 영상 생성 시작 요청은 가장 무거운 작업이므로 VERY_HEAVY(10분) timeout 적용.
export async function POST(request: NextRequest) {
  const body = await request.json()
  return proxyJson("/video/start", { method: "POST", body, timeoutMs: TIMEOUT.VERY_HEAVY })
}
