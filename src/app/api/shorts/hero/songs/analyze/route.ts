import { NextRequest, NextResponse } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/shorts/hero/songs/analyze — 업로드된 플리 영상 속 우리 곡 3개 후렴·드롭·BPM 분석.
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => null)
  if (!body) return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 })
  return proxyJson("/shorts/hero/songs/analyze", { method: "POST", body })
}
