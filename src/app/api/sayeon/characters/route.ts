import { NextRequest, NextResponse } from "next/server"
import { getSupabaseAdmin, SAYEON_CHARACTER_TABLE } from "@/lib/supabase"

// 사연 캐릭터 = CharacterSpec 8필드 + sheet_url/anchor. 비밀키는 서버사이드(Supabase admin).

interface SayeonSpec {
  gender?: string
  age?: string
  face?: string
  hair?: string
  outfit?: string
  accessories?: string
  signature?: string
  extra?: string
}

interface SayeonCharacterRow {
  id: string
  name: string
  spec: SayeonSpec | null
  sheet_url: string | null
  anchor: string | null
  created_at: string
}

// GET /api/sayeon/characters — 저장된 사연 캐릭터 목록
export async function GET() {
  try {
    const supabase = getSupabaseAdmin()
    const { data, error } = await supabase
      .from(SAYEON_CHARACTER_TABLE)
      .select("id, name, spec, sheet_url, anchor, created_at")
      .order("created_at", { ascending: false })
    if (error) {
      // 테이블 미생성/조회 실패 시에도 화면이 깨지지 않게 빈 목록 반환.
      return NextResponse.json({ characters: [] })
    }
    return NextResponse.json({ characters: (data ?? []) as SayeonCharacterRow[] })
  } catch {
    return NextResponse.json({ characters: [] })
  }
}

// POST /api/sayeon/characters — 새 사연 캐릭터 저장
export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { name, spec, sheet_url, anchor } = body as {
      name?: string
      spec?: SayeonSpec
      sheet_url?: string | null
      anchor?: string | null
    }
    if (!name?.trim()) {
      return NextResponse.json({ success: false, error: "캐릭터 이름이 필요해요" }, { status: 400 })
    }

    const row: SayeonCharacterRow = {
      id: `sayeon_${Date.now()}`,
      name: name.trim(),
      spec: spec ?? {},
      sheet_url: sheet_url || null,
      anchor: anchor || null,
      created_at: new Date().toISOString(),
    }

    const supabase = getSupabaseAdmin()
    const { error } = await supabase.from(SAYEON_CHARACTER_TABLE).insert(row)
    if (error) {
      return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    }
    return NextResponse.json({ success: true, character: row })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "알 수 없는 오류"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
