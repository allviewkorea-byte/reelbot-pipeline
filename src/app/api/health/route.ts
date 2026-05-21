import { NextResponse } from "next/server"

// "localhost"의 IPv6(::1) 해석 → 무한 대기 문제를 피하기 위해 IPv4 루프백으로 정규화.
const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(
  "://localhost",
  "://127.0.0.1",
)

export async function GET() {
  try {
    const res = await fetch(`${API_BASE}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
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
