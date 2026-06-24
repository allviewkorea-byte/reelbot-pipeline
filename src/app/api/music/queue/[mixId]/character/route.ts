import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"
import { TIMEOUT } from "@/lib/api-timeout"

// #50 인물(투명 PNG) 업로드(base64 JSON) → FastAPI /music/queue/{mixId}/character.
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ mixId: string }> },
) {
  const { mixId } = await params
  const body = await request.json()
  return proxyJson(`/music/queue/${encodeURIComponent(mixId)}/character`, {
    method: "POST",
    body,
    timeoutMs: TIMEOUT.HEAVY, // R2 업로드 여유
  })
}

// #50 인물 제거 → FastAPI DELETE /music/queue/{mixId}/character.
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ mixId: string }> },
) {
  const { mixId } = await params
  return proxyJson(`/music/queue/${encodeURIComponent(mixId)}/character`, { method: "DELETE" })
}
