import { proxyJson } from "@/lib/proxy"

// 최신 음악 트렌드 인사이트 — FastAPI /api/music/trends 로 프록시(대시보드/가이드 표시용).
export async function GET() {
  return proxyJson("/api/music/trends", { method: "GET" })
}
