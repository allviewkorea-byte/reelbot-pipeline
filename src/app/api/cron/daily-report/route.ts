import { NextRequest, NextResponse } from "next/server"
import { isAuthorizedCron } from "@/lib/cron-auth"
import { API_BASE } from "@/lib/proxy"

// 매일 점검 — vercel.json 크론(00:30 UTC = 09:30 KST, 음악 자동 제작이 끝난 뒤).
// 백엔드가 백그라운드로 수집·요약·저장하고 바로 응답 → Hobby 10초 안전.
export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  if (!isAuthorizedCron(req)) {
    return NextResponse.json({ success: false, error: "unauthorized" }, { status: 401 })
  }
  try {
    const res = await fetch(`${API_BASE}/api/system/daily-report/run`, {
      method: "POST", cache: "no-store", signal: AbortSignal.timeout(8_000),
      headers: { Authorization: `Bearer ${process.env.CRON_SECRET ?? ""}` },
    })
    const data = await res.json().catch(() => ({}))
    return NextResponse.json({ success: res.ok, ...data }, { status: res.ok ? 200 : 502 })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 502 })
  }
}
