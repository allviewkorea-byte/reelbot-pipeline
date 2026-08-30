import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 진행 중(+미확인 실패) 작업 목록(#36) — 대시보드 파이프라인·검토대기 진행 카드 폴링용.
// channel(운동 채널 2단계): 미지정이면 백엔드가 where 로 해석한다.
export const dynamic = "force-dynamic"

export async function GET(request: NextRequest) {
  const channel = request.nextUrl.searchParams.get("channel")
  const qs = channel ? `?channel=${encodeURIComponent(channel)}` : ""
  return proxyJson(`/api/music/jobs/active${qs}`, { method: "GET" })
}
