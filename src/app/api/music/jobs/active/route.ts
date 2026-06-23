import { proxyJson } from "@/lib/proxy"

// 진행 중(+미확인 실패) 작업 목록(#36) — 대시보드 파이프라인·검토대기 진행 카드 폴링용.
export const dynamic = "force-dynamic"

export async function GET() {
  return proxyJson("/api/music/jobs/active", { method: "GET" })
}
