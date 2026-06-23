import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"
import { TIMEOUT } from "@/lib/api-timeout"

// 썸네일 업로드(base64 JSON) → FastAPI /music/queue/{mixId}/thumbnail.
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ mixId: string }> },
) {
  const { mixId } = await params
  const body = await request.json()
  return proxyJson(`/music/queue/${encodeURIComponent(mixId)}/thumbnail`, {
    method: "POST",
    body,
    timeoutMs: TIMEOUT.HEAVY, // R2 업로드 여유
  })
}

// #33 C 이미지 제거 → FastAPI DELETE /music/queue/{mixId}/thumbnail.
export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ mixId: string }> },
) {
  const { mixId } = await params
  return proxyJson(`/music/queue/${encodeURIComponent(mixId)}/thumbnail`, { method: "DELETE" })
}
