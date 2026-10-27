import { NextRequest, NextResponse } from "next/server"
import { isAuthorizedCron } from "@/lib/cron-auth"
import { API_BASE } from "@/lib/proxy"

// 인스타 레퍼런스 하루 1회 수집 — vercel.json 크론(00:37 UTC = 09:37 KST, Vercel 이 CRON_SECRET 을 자동 헤더로).
// 백엔드가 백그라운드로 돌리고 바로 응답 → Hobby 10초 안전. 멱등: 오늘 이미 모았으면 수집은 건너뛰고 분석만.
export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  if (!isAuthorizedCron(req)) {
    return NextResponse.json({ success: false, error: "unauthorized" }, { status: 401 })
  }
  try {
    const res = await fetch(`${API_BASE}/insta/refs/collect`, { method: "POST", cache: "no-store", signal: AbortSignal.timeout(8_000) })
    const data = await res.json().catch(() => ({}))
    return NextResponse.json({ success: res.ok, ...data }, { status: res.ok ? 200 : 502 })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 502 })
  }
}
