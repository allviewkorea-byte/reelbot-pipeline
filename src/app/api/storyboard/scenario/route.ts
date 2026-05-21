import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"
import { TIMEOUT } from "@/lib/api-timeout"

// 시나리오 생성(백엔드 LLM)은 콘티 생성 동선의 첫 단계로 다소 길어질 수 있어 HEAVY(5분) 적용.
export async function POST(request: NextRequest) {
  const body = await request.json()
  return proxyJson("/storyboard/scenario", { method: "POST", body, timeoutMs: TIMEOUT.HEAVY })
}
