import { NextRequest, NextResponse } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/shorts/cast/generate { channel, role } — 8장 전체 생성(백그라운드 시작, 즉시 반환).
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => null)
  if (!body) return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 })
  return proxyJson("/shorts/cast/generate", { method: "POST", body: { channel: body.channel, role: body.role } })
}
