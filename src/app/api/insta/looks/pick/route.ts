import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/insta/looks/pick { video_id?, look_index? } — 레퍼런스 룩의 상품 고르기 시작(백그라운드).
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}))
  return proxyJson("/insta/looks/pick", { method: "POST", body })
}
