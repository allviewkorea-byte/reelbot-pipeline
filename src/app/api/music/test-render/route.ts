import { NextRequest, NextResponse } from "next/server"
import { API_BASE } from "@/lib/proxy"
import { TIMEOUT } from "@/lib/api-timeout"

// 테스트 영상 생성(#19) — Railway /api/music/test-render 로 프록시(동기).
// 즉석 10초 Remotion 렌더(유튜브 X, 큐 저장 X) → mp4 URL 반환. 렌더가 수십 초라
// maxDuration 을 넉넉히 둔다(Vercel 함수 한도 내).
export const dynamic = "force-dynamic"
export const maxDuration = 60

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}))
  try {
    const res = await fetch(`${API_BASE}/api/music/test-render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify(body ?? {}),
      signal: AbortSignal.timeout(TIMEOUT.VERY_HEAVY),
    })
    const data = await res.json().catch(() => ({}))
    return NextResponse.json(data, { status: res.status })
  } catch {
    return NextResponse.json(
      { detail: "테스트 렌더 트리거 실패(서버 미가동 또는 시간 초과)" },
      { status: 503 },
    )
  }
}
