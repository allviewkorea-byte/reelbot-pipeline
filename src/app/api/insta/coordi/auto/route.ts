import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/insta/coordi/auto { character_id } — 오늘의 코디 찾기(완전 자동): 레퍼런스 → 쿠팡 픽 → 착장(백그라운드).
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}))
  return proxyJson("/insta/coordi/auto", { method: "POST", body })
}
