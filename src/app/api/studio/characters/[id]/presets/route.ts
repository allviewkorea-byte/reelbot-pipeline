import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/studio/characters/{id}/presets { kind: hair|pose, items: [{key, line}] } — 프리셋 추가·삭제.
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const body = await req.json().catch(() => ({}))
  return proxyJson(`/studio/characters/${encodeURIComponent(id)}/presets`, { method: "POST", body })
}
