import { proxyJson } from "@/lib/proxy"

// GET /api/youtube-status — 백엔드 /api/youtube/status 프록시(유튜브 연동 여부).
export async function GET() {
  return proxyJson("/api/youtube/status", { method: "GET" })
}
