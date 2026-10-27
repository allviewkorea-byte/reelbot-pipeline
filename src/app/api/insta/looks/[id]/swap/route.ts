import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/insta/looks/{id}/swap { item_index, product_id } — 아이템 1등을 예비 후보로 교체.
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const body = await req.json().catch(() => ({}))
  return proxyJson(`/insta/looks/${encodeURIComponent(id)}/swap`, { method: "POST", body })
}
