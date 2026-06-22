import { NextRequest, NextResponse } from "next/server"
import { isAuthorizedCron } from "@/lib/cron-auth"
import { API_BASE } from "@/lib/proxy"

// 음악 트렌드 분석 cron(주 2회) — Railway /api/music/trends/analyze 를 fire-and-forget 트리거.
// 백엔드가 BackgroundTasks 로 즉시 반환하므로 Vercel Hobby 10초 안에 끝난다.
// CRON_SECRET(Authorization: Bearer)로 보호(백곰/음악 produce 와 동일 패턴).
export const dynamic = "force-dynamic"
export const maxDuration = 60

async function trigger(req: NextRequest) {
  if (!isAuthorizedCron(req)) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 })
  }
  const secret = process.env.CRON_SECRET || ""
  try {
    const res = await fetch(`${API_BASE}/api/music/trends/analyze`, {
      method: "POST",
      headers: { Authorization: `Bearer ${secret}`, "Content-Type": "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    })
    const data = await res.json().catch(() => ({}))
    return NextResponse.json({ ok: res.ok, triggered: data }, { status: res.status })
  } catch {
    return NextResponse.json(
      { ok: false, error: "Railway 트렌드 분석 트리거 실패" },
      { status: 502 },
    )
  }
}

export async function GET(req: NextRequest) {
  return trigger(req)
}
export async function POST(req: NextRequest) {
  return trigger(req)
}
