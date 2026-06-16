import { NextRequest, NextResponse } from "next/server"
import { API_BASE } from "@/lib/proxy"
import { TIMEOUT } from "@/lib/api-timeout"

// GET /api/cast/status?role= — 역할별 멀티 아스펙트 생성 진행상태.
// 백엔드 /sayeon/cast-status 프록시. status: idle|running|done|failed + generated/failed/total.
export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  const role = req.nextUrl.searchParams.get("role") || ""
  if (!role) {
    return NextResponse.json({ success: false, error: "role 이 필요합니다" }, { status: 400 })
  }
  try {
    const data = await fetch(`${API_BASE}/sayeon/cast-status?role=${encodeURIComponent(role)}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT.QUICK),
    }).then((r) => r.json())
    return NextResponse.json({ success: true, ...data })
  } catch {
    // 백엔드 미연결 → idle 로 처리(폴링이 멈추지 않게 화면에서 판단).
    return NextResponse.json({ success: true, role, status: "idle", generated: [], failed: [], total: 7 })
  }
}
