import { NextRequest, NextResponse } from "next/server"
import { API_BASE } from "@/lib/proxy"
import { TIMEOUT } from "@/lib/api-timeout"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"
import { getSupabaseAdmin, SAYEON_CAST_TABLE } from "@/lib/supabase"

// POST /api/cast/generate { role } — 역할별 멀티 아스펙트 생성을 **논블로킹**으로 시작.
//  ① 백엔드(/sayeon/cast-sheet)가 즉시 status=running 반환(백그라운드 생성).
//  ② 메타 upsert(status=draft — 재생성 시 승인 초기화).
// 진행은 GET /api/cast/status?role= 로 폴링, 아스펙트는 GET /api/cast 에 차오른다.
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest) {
  let role = ""
  let channelId = BAEKGOM_CHANNEL_ID
  try {
    const body = await req.json()
    role = typeof body?.role === "string" ? body.role.trim() : ""
    if (typeof body?.channelId === "string" && body.channelId) channelId = body.channelId
  } catch {
    return NextResponse.json({ success: false, error: "Invalid JSON" }, { status: 400 })
  }
  if (!role) {
    return NextResponse.json({ success: false, error: "role 이 필요합니다" }, { status: 400 })
  }

  try {
    // ① 논블로킹 시작 — 백엔드가 즉시 반환(생성은 백그라운드).
    const res = await fetch(`${API_BASE}/sayeon/cast-sheet`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channel_id: channelId, role }),
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT.QUICK),
    })
    const data = await res.json()
    if (!res.ok) {
      const msg = typeof data?.detail === "string" ? data.detail : "생성 시작 실패"
      return NextResponse.json({ success: false, error: msg }, { status: 502 })
    }

    // ② 메타 upsert(role PK). 재생성은 status=draft 로 되돌려 재확정을 요구.
    try {
      const supabase = getSupabaseAdmin()
      const { error } = await supabase.from(SAYEON_CAST_TABLE).upsert(
        {
          role,
          status: "draft",
          sheet_filename: "front.png",
          updated_at: new Date().toISOString(),
        },
        { onConflict: "role" },
      )
      if (error) {
        console.error("[cast/generate] sayeon_cast upsert 실패:", {
          message: error.message,
          details: error.details,
          hint: error.hint,
          code: error.code,
        })
      }
    } catch (e) {
      console.error("[cast/generate] 메타 저장 예외:", e)
    }

    return NextResponse.json({ success: true, role, status: data.status ?? "running" })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "알 수 없는 오류"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
