import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// GET /api/insta/outfits?character_id= — 최근 착장 / POST { character_id, products, options } — 착장 만들기(백그라운드).
export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  const cid = req.nextUrl.searchParams.get("character_id") || "chaei"
  return proxyJson(`/insta/outfits?character_id=${encodeURIComponent(cid)}&limit=12`, { method: "GET" })
}

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}))
  return proxyJson("/insta/outfits", { method: "POST", body })
}
