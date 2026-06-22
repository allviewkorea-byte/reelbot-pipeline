import { proxyJson } from "@/lib/proxy"

// 검토 대기(pending) 음악 영상 큐 — FastAPI /music/queue 로 프록시.
export async function GET() {
  return proxyJson("/music/queue", { method: "GET" })
}
