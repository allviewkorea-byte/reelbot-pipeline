import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 최근 완료/실패 작업(#36) — 대시보드 통계용.
export const dynamic = "force-dynamic"

export async function GET(request: NextRequest) {
  const limit = request.nextUrl.searchParams.get("limit") || "20"
  return proxyJson(`/api/music/jobs/history?limit=${encodeURIComponent(limit)}`, { method: "GET" })
}
