import { NextRequest, NextResponse } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/shorts/cast/aspect { channel, role, aspect } — 1장만 재생성(동기, Vercel Hobby 상한 60초).
export const dynamic = "force-dynamic"
export const maxDuration = 60

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => null)
  if (!body) return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 })
  return proxyJson("/shorts/cast/aspect", {
    method: "POST",
    body: { channel: body.channel, role: body.role, aspect: body.aspect },
    timeoutMs: 55_000,
  })
}
