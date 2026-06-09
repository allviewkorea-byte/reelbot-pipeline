import { NextRequest, NextResponse } from "next/server"
import { getSupabaseAdmin, SAYEON_CHARACTER_TABLE } from "@/lib/supabase"

// GET /api/sayeon/characters/[id] — 단건 조회
export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params
    const supabase = getSupabaseAdmin()
    const { data, error } = await supabase
      .from(SAYEON_CHARACTER_TABLE)
      .select("id, name, spec, sheet_url, anchor, created_at")
      .eq("id", id)
      .maybeSingle()
    if (error || !data) {
      return NextResponse.json({ success: false, error: "캐릭터를 찾을 수 없어요" }, { status: 404 })
    }
    return NextResponse.json({ success: true, character: data })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "알 수 없는 오류"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}

// PATCH /api/sayeon/characters/[id] — 시트 URL/앵커 갱신(생성 후 시트 재사용 저장용)
export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params
    const body = await req.json()
    const { sheet_url, anchor } = body as { sheet_url?: string; anchor?: string }

    const patch: Record<string, string> = {}
    if (sheet_url) patch.sheet_url = sheet_url
    if (anchor) patch.anchor = anchor
    if (Object.keys(patch).length === 0) {
      return NextResponse.json({ success: false, error: "갱신할 값이 없어요" }, { status: 400 })
    }

    const supabase = getSupabaseAdmin()
    const { data, error } = await supabase
      .from(SAYEON_CHARACTER_TABLE)
      .update(patch)
      .eq("id", id)
      .select("id")
    if (error) {
      return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    }
    if (!data || data.length === 0) {
      return NextResponse.json({ success: false, error: "캐릭터를 찾을 수 없어요" }, { status: 404 })
    }
    return NextResponse.json({ success: true })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "알 수 없는 오류"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
