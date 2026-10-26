import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/studio/characters/{id}/generate { items: [{role, prompt?, count?}] } — 후보 생성 시작(백그라운드).
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const body = await req.json().catch(() => ({}))
  return proxyJson(`/studio/characters/${encodeURIComponent(id)}/generate`, { method: "POST", body })
}
