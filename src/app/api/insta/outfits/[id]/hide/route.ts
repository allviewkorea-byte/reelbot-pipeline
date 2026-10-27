import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/insta/outfits/{id}/hide { reason } — 착장 내리기(숨김 + 사유).
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const body = await req.json().catch(() => ({}))
  return proxyJson(`/insta/outfits/${encodeURIComponent(id)}/hide`, { method: "POST", body })
}
