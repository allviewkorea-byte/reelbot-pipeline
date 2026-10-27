import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// GET /api/insta/collections — 최근 컬렉션 릴스 / POST { character_id, n } — 컬렉션 릴스 만들기(A3, 백그라운드).
export const dynamic = "force-dynamic"

export async function GET() {
  return proxyJson("/insta/collections?limit=6", { method: "GET" })
}

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}))
  return proxyJson("/insta/collections", { method: "POST", body })
}
