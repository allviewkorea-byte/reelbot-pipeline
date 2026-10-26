import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// GET/POST /api/studio/characters/{id}/measurements — 캐릭터 실측 치수(착장 핏 계산 입력).
export const dynamic = "force-dynamic"

export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return proxyJson(`/studio/characters/${encodeURIComponent(id)}/measurements`, { method: "GET" })
}

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const body = await req.json().catch(() => ({}))
  return proxyJson(`/studio/characters/${encodeURIComponent(id)}/measurements`, { method: "POST", body })
}
