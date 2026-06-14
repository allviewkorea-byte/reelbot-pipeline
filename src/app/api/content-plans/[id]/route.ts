import { NextRequest, NextResponse } from "next/server"
import { deleteContentPlan } from "@/lib/supabase"

// DELETE /api/content-plans/[id] — 콘텐츠 플랜 삭제.
export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params
  try {
    await deleteContentPlan(id)
    return NextResponse.json({ success: true })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
