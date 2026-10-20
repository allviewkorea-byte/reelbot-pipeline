import { NextRequest, NextResponse } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/shorts/test-run { channel, days, compare_seedance } — 비공개 테스트 제작 시작(백그라운드).
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => null)
  if (!body) return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 })
  return proxyJson("/shorts/test-run", {
    method: "POST",
    body: { channel: body.channel, days: body.days, compare_seedance: body.compare_seedance },
  })
}
