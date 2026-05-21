import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"
import { TIMEOUT } from "@/lib/api-timeout"

// 단일 씬 콘티 재생성도 이미지 생성을 동반하므로 HEAVY(5분) timeout 적용.
export async function POST(request: NextRequest) {
  const body = await request.json()
  return proxyJson("/storyboard/regenerate", { method: "POST", body, timeoutMs: TIMEOUT.HEAVY })
}
