import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/insta/coordi { character_id, products, mode: only|fill, options } — 내 상품으로 코디(백그라운드).
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}))
  return proxyJson("/insta/coordi", { method: "POST", body })
}
