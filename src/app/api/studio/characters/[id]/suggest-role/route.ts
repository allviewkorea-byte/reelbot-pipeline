import { NextRequest, NextResponse } from "next/server"
import { API_BASE } from "@/lib/proxy"

// POST /api/studio/characters/{id}/suggest-role (multipart: file) — 비전 AI 역할 추천(저장 안 함).
// ⚠️ Vercel 함수 본문 한도 4.5MB — 화면이 3.8MB 넘는 파일은 미리 줄여 보낸다.
export const dynamic = "force-dynamic"
export const maxDuration = 60

export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  let form: FormData
  try {
    form = await req.formData()
  } catch {
    return NextResponse.json({ detail: "업로드 형식이 올바르지 않아요." }, { status: 400 })
  }
  const file = form.get("file")
  if (!(file instanceof File) || file.size === 0) {
    return NextResponse.json({ detail: "이미지 파일이 없어요." }, { status: 400 })
  }
  const out = new FormData()
  out.append("file", file, file.name)
  try {
    const res = await fetch(`${API_BASE}/studio/characters/${encodeURIComponent(id)}/suggest-role`, {
      method: "POST",
      body: out,
      cache: "no-store",
      signal: AbortSignal.timeout(55_000),
    })
    const data = await res.json().catch(() => ({ detail: "백엔드 응답을 읽을 수 없어요." }))
    return NextResponse.json(data, { status: res.status })
  } catch {
    return NextResponse.json({ detail: "백엔드 서버에 연결할 수 없습니다." }, { status: 503 })
  }
}
