import { NextResponse } from "next/server"
import { TIMEOUT } from "@/lib/api-timeout"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"

export async function GET() {
  try {
    const res = await fetch(`${API_BASE}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT.HEALTH),
    })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch {
    return NextResponse.json(
      { status: "error", error: "백엔드 서버가 응답하지 않습니다." },
      { status: 503 },
    )
  }
}
