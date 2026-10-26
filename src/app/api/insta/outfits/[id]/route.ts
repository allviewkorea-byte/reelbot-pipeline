import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// GET /api/insta/outfits/{id} — 착장 1건(기획·검수·이미지 URL).
export const dynamic = "force-dynamic"

export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return proxyJson(`/insta/outfits/${encodeURIComponent(id)}`, { method: "GET" })
}
