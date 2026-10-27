import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/insta/collections/{id}/make — 미리보기에서 확인한 기획 그대로 릴스 만들기.
export const dynamic = "force-dynamic"

export async function POST(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  return proxyJson(`/insta/collections/${encodeURIComponent(id)}/make`, { method: "POST" })
}
