import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/insta/refs/collect?force=1 — 레퍼런스 수집·분석 시작(백그라운드, 오늘 이미 했으면 수집은 건너뜀).
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest) {
  const force = req.nextUrl.searchParams.get("force") === "1"
  return proxyJson(`/insta/refs/collect${force ? "?force=true" : ""}`, { method: "POST" })
}
