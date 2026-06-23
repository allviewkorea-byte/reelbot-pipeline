import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"
import { TIMEOUT } from "@/lib/api-timeout"

// #32 다국어 — POST: 생성(또는 캐시) / PUT: 수정 저장. FastAPI /music/queue/{mixId}/localize.
export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ mixId: string }> },
) {
  const { mixId } = await params
  // GPT 번역(제목·설명·가사 10개 언어)이라 오래 걸림 → HEAVY 타임아웃.
  return proxyJson(`/music/queue/${encodeURIComponent(mixId)}/localize`, {
    method: "POST",
    timeoutMs: TIMEOUT.HEAVY,
  })
}

export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ mixId: string }> },
) {
  const { mixId } = await params
  const body = await req.json()
  return proxyJson(`/music/queue/${encodeURIComponent(mixId)}/localize`, {
    method: "PUT",
    body,
  })
}
