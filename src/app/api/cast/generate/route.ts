import { NextRequest, NextResponse } from "next/server"
import { API_BASE } from "@/lib/proxy"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"
import { getSupabaseAdmin, SAYEON_CAST_TABLE } from "@/lib/supabase"

// POST /api/cast/generate { role } — 역할별 캐스트 시트 1장 생성(재생성).
//  ① 백엔드(/sayeon/cast-sheet)가 동기 생성 → R2(역할별 고정 파일명)에 저장.
//  ② 성공 시 Supabase sayeon_cast 에 메타 upsert(status=draft — 재생성 시 승인 초기화).
// 생성은 수십 초 걸릴 수 있어 함수 시간을 넉넉히 둔다(Vercel Hobby 상한 60초).
export const dynamic = "force-dynamic"
export const maxDuration = 60

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
    // ① 백엔드 동기 생성. Vercel 함수 상한(60초)에 맞춰 55초로 끊고, 초과해도 R2엔
    //    업로드가 끝나 있을 수 있어 다음 조회(GET /api/cast)에서 복구된다.
    const res = await fetch(`${API_BASE}/sayeon/cast-sheet`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channel_id: channelId, role }),
      cache: "no-store",
      signal: AbortSignal.timeout(55_000),
    })
    const data = await res.json()
    if (!res.ok) {
      const msg = typeof data?.detail === "string" ? data.detail : "시트 생성 실패"
      return NextResponse.json({ success: false, error: msg }, { status: 502 })
    }

    // ② 메타 upsert(role PK). 재생성은 status=draft 로 되돌려 재확정을 요구.
    try {
      const supabase = getSupabaseAdmin()
      const { error } = await supabase.from(SAYEON_CAST_TABLE).upsert(
        {
          role: data.role ?? role,
          name: data.name ?? null,
          animal: data.animal ?? null,
          sheet_filename: data.filename ?? null,
          status: "draft",
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
      // 메타 저장 실패해도 시트는 R2에 저장됨 → 다음 조회에서 노출. 로깅만.
      console.error("[cast/generate] 메타 저장 예외(시트는 R2 저장됨):", e)
    }

    return NextResponse.json({ success: true, role: data.role ?? role, sheet_url: data.sheet_url ?? null })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "알 수 없는 오류"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
