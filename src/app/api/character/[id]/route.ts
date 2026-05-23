import { NextRequest, NextResponse } from "next/server"
import { getSupabaseAdmin, CHARACTER_TABLE, CHARACTER_BUCKET } from "@/lib/supabase"

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params
    const supabase = getSupabaseAdmin()

    const { data, error } = await supabase
      .from(CHARACTER_TABLE)
      .delete()
      .eq("id", id)
      .select("id")
    if (error) {
      return NextResponse.json({ success: false, error: error.message }, { status: 500 })
    }
    if (!data || data.length === 0) {
      return NextResponse.json({ success: false, error: "캐릭터를 찾을 수 없어요" }, { status: 404 })
    }

    // Storage 이미지도 정리한다. 실패해도 메타데이터 삭제는 성공으로 처리.
    await supabase.storage
      .from(CHARACTER_BUCKET)
      .remove([`${id}/front.png`, `${id}/side.png`, `${id}/back.png`])

    return NextResponse.json({ success: true })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "알 수 없는 오류"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
