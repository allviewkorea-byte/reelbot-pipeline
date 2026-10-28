import { proxyJson } from "@/lib/proxy"

// GET /api/system/daily-report — 최신 매일 점검 리포트(요약 + 유튜브 성과).
export const dynamic = "force-dynamic"

export async function GET() {
  return proxyJson("/api/system/daily-report", { method: "GET", timeoutMs: 15_000 })
}
