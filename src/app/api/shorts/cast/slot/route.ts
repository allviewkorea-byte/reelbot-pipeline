import { NextRequest, NextResponse } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/shorts/cast/slot { channel, role, aspect, cols?, crop?, labels? } — 시트 칸 수·자르지 않기·칸 라벨.
export const dynamic = "force-dynamic"
export const maxDuration = 60

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => null)
  if (!body) return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 })
  return proxyJson("/shorts/cast/slot", {
    method: "POST",
    body: { channel: body.channel, role: body.role, aspect: body.aspect, cols: body.cols, crop: body.crop, labels: body.labels },
    timeoutMs: 55_000,
  })
}
