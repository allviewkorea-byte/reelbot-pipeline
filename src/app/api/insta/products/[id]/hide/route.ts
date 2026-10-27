import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/insta/products/{id}/hide { reason } — 상품 내리기(숨김 + 사유, 예: 판매자 요청).
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const body = await req.json().catch(() => ({}))
  return proxyJson(`/insta/products/${encodeURIComponent(id)}/hide`, { method: "POST", body })
}
