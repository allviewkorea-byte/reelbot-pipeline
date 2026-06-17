import { NextRequest, NextResponse } from "next/server"
import { API_BASE } from "@/lib/proxy"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"

// POST /api/cast/aspect { role, aspect } — 아스펙트 1장만 재생성(동기).
// 백엔드(/sayeon/cast-aspect)가 그 1장만 재생성·R2 덮어쓰기 → ?v= 붙은 새 URL 반환.
// 1장이라 동기(~10초). 함수 시간을 넉넉히 둔다(Vercel Hobby 상한 60초).
export const dynamic = "force-dynamic"
export const maxDuration = 60

const ASPECTS = new Set([
  "front", "threequarter", "side",
  "expr_joy", "expr_sad", "expr_angry", "expr_surprised",
])

export async function POST(req: NextRequest) {
  let role = ""
  let aspect = ""
  try {
    const body = await req.json()
    role = typeof body?.role === "string" ? body.role.trim() : ""
    aspect = typeof body?.aspect === "string" ? body.aspect.trim() : ""
  } catch {
    return NextResponse.json({ success: false, error: "Invalid JSON" }, { status: 400 })
  }
  if (!role || !ASPECTS.has(aspect)) {
    return NextResponse.json({ success: false, error: "role/aspect 가 올바르지 않습니다" }, { status: 400 })
  }
  // channelId 는 호환용(아스펙트 키는 채널 무관) — 검증만 하고 백엔드엔 안 넘김.
  void BAEKGOM_CHANNEL_ID

  try {
    const res = await fetch(`${API_BASE}/sayeon/cast-aspect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role, aspect }),
      cache: "no-store",
      signal: AbortSignal.timeout(55_000),
    })
    const data = await res.json()
    if (!res.ok) {
      const msg = typeof data?.detail === "string" ? data.detail : "재생성 실패"
      return NextResponse.json({ success: false, error: msg }, { status: 502 })
    }
    return NextResponse.json({
      success: true,
      role: data.role ?? role,
      aspect: data.aspect ?? aspect,
      url: data.url ?? null,
      warning: data.warning ?? null,
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "알 수 없는 오류"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
