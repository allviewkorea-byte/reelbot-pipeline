import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 폰 GPT 프롬프트 재생성 → FastAPI GET /music/queue/{mixId}/gpt-prompt.
export const dynamic = "force-dynamic"

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ mixId: string }> },
) {
  const { mixId } = await params
  return proxyJson(`/music/queue/${encodeURIComponent(mixId)}/gpt-prompt`, { method: "GET" })
}
