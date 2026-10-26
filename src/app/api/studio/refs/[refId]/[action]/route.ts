import { NextRequest, NextResponse } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/studio/refs/{refId}/confirm|discard — 확정 바꾸기(이전 확정은 후보로) / 버리기.
export const dynamic = "force-dynamic"

const ACTIONS = new Set(["confirm", "discard"])

export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ refId: string; action: string }> },
) {
  const { refId, action } = await params
  if (!ACTIONS.has(action) || !/^\d+$/.test(refId)) {
    return NextResponse.json({ detail: "잘못된 요청이에요." }, { status: 400 })
  }
  return proxyJson(`/studio/refs/${refId}/${action}`, { method: "POST" })
}
