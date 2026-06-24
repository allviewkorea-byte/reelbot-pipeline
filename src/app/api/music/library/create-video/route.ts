import { NextRequest, NextResponse } from "next/server"
import { API_BASE } from "@/lib/proxy"

// 선택곡으로 영상 만들기 시작(#48) — Railway /api/music/library/create-video 트리거(비동기).
// 백엔드가 BackgroundTasks 로 job_id 즉시 반환. 완료 시 검토 큐(pending)에 적재된다.
export const dynamic = "force-dynamic"
export const maxDuration = 60

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}))
  try {
    const res = await fetch(`${API_BASE}/api/music/library/create-video`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify(body ?? {}),
      signal: AbortSignal.timeout(30_000),
    })
    const data = await res.json().catch(() => ({}))
    return NextResponse.json(data, { status: res.status })
  } catch {
    return NextResponse.json({ detail: "영상 만들기 시작 실패(서버 미가동?)" }, { status: 503 })
  }
}
