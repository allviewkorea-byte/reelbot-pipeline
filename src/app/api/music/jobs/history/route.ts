import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 최근 완료/실패 작업(#36) — 대시보드 통계용.
// channel(운동 채널 2단계): 미지정이면 백엔드가 where 로 해석한다.
export const dynamic = "force-dynamic"

export async function GET(request: NextRequest) {
  const limit = request.nextUrl.searchParams.get("limit") || "20"
  const channel = request.nextUrl.searchParams.get("channel")
  const qs = `?limit=${encodeURIComponent(limit)}${channel ? `&channel=${encodeURIComponent(channel)}` : ""}`
  return proxyJson(`/api/music/jobs/history${qs}`, { method: "GET" })
}
