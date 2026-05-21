import { NextResponse } from "next/server"
import { TIMEOUT } from "./api-timeout"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"

// FastAPI 백엔드로 요청을 그대로 전달하는 공통 proxy 헬퍼.
// timeoutMs 미지정 시 일반 조회/저장 기준(QUICK, 30초)을 적용한다. 콘티/영상 등
// 오래 걸리는 작업은 호출부에서 TIMEOUT.HEAVY / VERY_HEAVY 를 넘겨야 한다.
export async function proxyJson(
  path: string,
  init: { method: "GET" | "POST"; body?: unknown; timeoutMs?: number },
): Promise<NextResponse> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: init.method,
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
      signal: AbortSignal.timeout(init.timeoutMs ?? TIMEOUT.QUICK),
    })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch {
    return NextResponse.json(
      { detail: "백엔드 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요." },
      { status: 503 },
    )
  }
}
