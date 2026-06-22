import { NextRequest, NextResponse } from "next/server"
import { isAuthorizedCron } from "@/lib/cron-auth"
import { API_BASE } from "@/lib/proxy"

// 음악 채널 자동화 cron — 주제→음원→영상→검토 대기 큐 적재를 트리거한다.
// Railway 의 /api/music/produce 가 BackgroundTasks 로 즉시 반환(fire-and-forget)하므로
// 이 라우트는 Railway 작업 완료를 기다리지 않는다(Vercel Hobby 10초 안에 끝남).
// 백곰 produce-due 와 동일하게 CRON_SECRET(Authorization: Bearer) 로 보호한다.
export const dynamic = "force-dynamic"
export const maxDuration = 60

async function trigger(req: NextRequest) {
  if (!isAuthorizedCron(req)) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 })
  }
  const secret = process.env.CRON_SECRET || ""
  try {
    const res = await fetch(`${API_BASE}/api/music/produce`, {
      method: "POST",
      headers: { Authorization: `Bearer ${secret}`, "Content-Type": "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    })
    const data = await res.json().catch(() => ({}))
    return NextResponse.json({ ok: res.ok, triggered: data }, { status: res.status })
  } catch {
    return NextResponse.json(
      { ok: false, error: "Railway produce 트리거 실패(서버 미가동?)" },
      { status: 502 },
    )
  }
}

// Vercel Cron 은 GET, 외부(cron-job.org)는 GET/POST 모두 가능 — 둘 다 지원.
export async function GET(req: NextRequest) {
  return trigger(req)
}
export async function POST(req: NextRequest) {
  return trigger(req)
}
