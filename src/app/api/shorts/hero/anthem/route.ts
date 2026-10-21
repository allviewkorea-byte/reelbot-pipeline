import { NextRequest, NextResponse } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/shorts/hero/anthem — 쿵쿵따 스타디움 운동 앤섬(연주곡) Suno 1회=2클립 생성.
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => null)
  if (!body) return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 })
  return proxyJson("/shorts/hero/anthem", { method: "POST", body })
}
