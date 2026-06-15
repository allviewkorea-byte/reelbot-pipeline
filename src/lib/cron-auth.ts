import type { NextRequest } from "next/server"

// 크론 엔드포인트 보호 — Authorization: Bearer ${CRON_SECRET} 검증.
// Vercel Cron 은 CRON_SECRET 을 자동으로 이 헤더로 전송하고, 외부 크론(cron-job.org)은
// 잡 설정에서 동일 헤더를 넣는다. CRON_SECRET 미설정 시 무조건 거부(안전 기본값).
export function isAuthorizedCron(req: NextRequest): boolean {
  const secret = process.env.CRON_SECRET
  if (!secret) return false
  return req.headers.get("authorization") === `Bearer ${secret}`
}
