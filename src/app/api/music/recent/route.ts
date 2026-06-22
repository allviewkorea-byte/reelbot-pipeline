import { proxyJson } from "@/lib/proxy"

// 최근 업로드된 음악 영상(공개 완료) — FastAPI /music/recent 로 프록시(대시보드 마퀴용).
export async function GET() {
  return proxyJson("/music/recent", { method: "GET" })
}
