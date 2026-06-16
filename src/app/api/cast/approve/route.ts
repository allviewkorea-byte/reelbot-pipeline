import { NextRequest, NextResponse } from "next/server"
import { getSupabaseAdmin, SAYEON_CAST_TABLE } from "@/lib/supabase"

// POST /api/cast/approve { role } — 해당 캐스트를 승인(status=approved) 처리.
// 시트 생성 후 호출되는 흐름이라 row 가 이미 존재한다(없으면 upsert 로 생성).
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest) {
  let role = ""
  try {
    const body = await req.json()
    role = typeof body?.role === "string" ? body.role.trim() : ""
  } catch {
    return NextResponse.json({ success: false, error: "Invalid JSON" }, { status: 400 })
  }
  if (!role) {
    return NextResponse.json({ success: false, error: "role 이 필요합니다" }, { status: 400 })
  }

  try {
    const supabase = getSupabaseAdmin()
    // 제공한 컬럼만 갱신(name/animal/sheet_filename 보존). updated_at 동반.
    const { error } = await supabase
      .from(SAYEON_CAST_TABLE)
      .upsert(
        { role, status: "approved", updated_at: new Date().toISOString() },
        { onConflict: "role" },
      )
    if (error) {
      return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    }
    return NextResponse.json({ success: true, role, status: "approved" })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "알 수 없는 오류"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
