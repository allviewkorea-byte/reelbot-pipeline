import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/insta/outfits/{id}/decision { decision: approved|rejected, reason? } — 이 코디 좋아요 / 다른 코디.
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const body = await req.json().catch(() => ({}))
  return proxyJson(`/insta/outfits/${encodeURIComponent(id)}/decision`, { method: "POST", body })
}
