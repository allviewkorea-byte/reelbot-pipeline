import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 사연 end-to-end 생성은 백그라운드 job 이라 job_id 를 즉시 반환한다(QUICK).
// 실제 진행은 /api/jobs/{id}/status 폴링으로 추적한다.
export async function POST(request: NextRequest) {
  const body = await request.json()
  return proxyJson("/sayeon/generate", { method: "POST", body })
}
