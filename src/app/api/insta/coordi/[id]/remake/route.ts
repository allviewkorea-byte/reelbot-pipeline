import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/insta/coordi/{outfitId}/remake — 같은 상품(교체 반영), 새 장면으로 다시 입히기.
export const dynamic = "force-dynamic"

export async function POST(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return proxyJson(`/insta/coordi/${encodeURIComponent(id)}/remake`, { method: "POST" })
}
