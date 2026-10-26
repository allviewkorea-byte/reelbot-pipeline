import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// GET /api/studio/characters/{id}/plan?role= — 그 역할의 기본 프롬프트(고급 보기).
export const dynamic = "force-dynamic"

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const role = req.nextUrl.searchParams.get("role") || ""
  return proxyJson(`/studio/characters/${encodeURIComponent(id)}/plan?role=${encodeURIComponent(role)}`, { method: "GET" })
}
