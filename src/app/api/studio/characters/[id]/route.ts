import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// GET /api/studio/characters/{id} — 캐릭터 + 역할별 확정·후보 + 준비 상태(01_face·02_body).
export const dynamic = "force-dynamic"

export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return proxyJson(`/studio/characters/${encodeURIComponent(id)}`, { method: "GET" })
}
