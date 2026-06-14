import { proxyJson } from "@/lib/proxy"

// GET /api/jobs/active — 백엔드 /jobs/active 프록시(현재/최근 job 1건, 없으면 null).
// 노드그래프 폴링용. 백엔드 에러/미응답 시 proxyJson 이 503+detail 반환 → 컴포넌트가 유휴 폴백.
export async function GET() {
  return proxyJson("/jobs/active", { method: "GET" })
}
