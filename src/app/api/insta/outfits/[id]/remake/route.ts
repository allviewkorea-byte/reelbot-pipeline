import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/insta/outfits/{id}/remake — 같은 상품, 새 기획으로 다시 만들기.
export const dynamic = "force-dynamic"

export async function POST(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return proxyJson(`/insta/outfits/${encodeURIComponent(id)}/remake`, { method: "POST" })
}
