import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 메인 대시보드 요약(상태등·오늘 회차·숫자 4개·최근 7회차·알림) — FastAPI 프록시(읽기 전용).
// Suno 잔액 등 외부 조회는 백엔드가 짧은 타임아웃·5분 캐시로 처리한다. 비밀키는 서버에만 있다.
// channel 미지정이면 백엔드가 where 로 해석한다.
export const dynamic = "force-dynamic"

export async function GET(request: NextRequest) {
  const channel = request.nextUrl.searchParams.get("channel")
  const qs = channel ? `?channel=${encodeURIComponent(channel)}` : ""
  return proxyJson(`/api/music/dashboard/summary${qs}`, { method: "GET" })
}
