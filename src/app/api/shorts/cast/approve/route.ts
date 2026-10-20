import { NextRequest, NextResponse } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/shorts/cast/approve { channel, role, approved } — 확정/해제(R2 state.json).
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => null)
  if (!body) return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 })
  return proxyJson("/shorts/cast/approve", {
    method: "POST",
    body: { channel: body.channel, role: body.role, approved: !!body.approved },
  })
}
