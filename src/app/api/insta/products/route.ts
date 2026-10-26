import { NextRequest, NextResponse } from "next/server"
import { API_BASE } from "@/lib/proxy"

// POST /api/insta/products (multipart: file, batch, n) — 상품 사진 1장 업로드 + 비전 AI 종류 추천.
// ⚠️ Vercel 함수 본문 한도 4.5MB — 화면이 3.8MB 넘는 파일은 미리 줄여 보낸다(한 장씩 보냄).
export const dynamic = "force-dynamic"
export const maxDuration = 60

export async function POST(req: NextRequest) {
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
  for (const k of ["batch", "n"]) {
    const v = form.get(k)
    if (typeof v === "string" && v) out.append(k, v)
  }
  try {
    const res = await fetch(`${API_BASE}/insta/products`, {
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
