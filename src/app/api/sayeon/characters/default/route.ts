import { NextResponse } from "next/server"
import { getSupabaseAdmin, SAYEON_CHARACTER_TABLE } from "@/lib/supabase"

// 감성 사연 채널용 기본 캐릭터(고정 스펙 — 랜덤 아님). 공감 가는 한국 20대 여성.
// 매 영상 같은 인물로 일관성을 유지하기 위한 시드값.
const DEFAULT_SPEC = {
  gender: "woman",
  age: "early 20s",
  hair: "long straight dark brown hair",
  face: "warm soft features, expressive eyes",
  outfit: "cozy cream knit sweater",
  accessories: "simple small stud earrings",
  signature: "warm relatable everyday girl",
  extra: "",
}

const COLS = "id, name, spec, sheet_url, anchor, created_at"

// GET /api/sayeon/characters/default — 기본 캐릭터 조회(없으면 고정 스펙으로 1회 시드).
// 이후 이 캐릭터를 계속 재사용한다(생성된 시트는 별도 PATCH 로 저장되어 재사용).
export async function GET() {
  try {
    const supabase = getSupabaseAdmin()
    const { data, error } = await supabase
      .from(SAYEON_CHARACTER_TABLE)
      .select(COLS)
      .eq("is_default", true)
      .order("created_at", { ascending: true })
      .limit(1)
    if (!error && data && data.length > 0) {
      return NextResponse.json({ success: true, character: data[0] })
    }

    // 기본 캐릭터가 없으면 고정 스펙으로 시드(랜덤 재생성 금지 — 일관성 유지).
    const row = {
      id: `sayeon_default_${Date.now()}`,
      name: "기본 캐릭터",
      spec: DEFAULT_SPEC,
      sheet_url: null as string | null,
      anchor: null as string | null,
      is_default: true,
      created_at: new Date().toISOString(),
    }
    const { error: insErr } = await supabase.from(SAYEON_CHARACTER_TABLE).insert(row)
    if (insErr) {
      return NextResponse.json({ success: false, error: insErr.message }, { status: 500 })
    }
    return NextResponse.json({
      success: true,
      character: {
        id: row.id,
        name: row.name,
        spec: row.spec,
        sheet_url: row.sheet_url,
        anchor: row.anchor,
        created_at: row.created_at,
      },
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "알 수 없는 오류"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
