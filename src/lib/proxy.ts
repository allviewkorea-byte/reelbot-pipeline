import { NextResponse } from "next/server"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"

// FastAPI 백엔드로 요청을 그대로 전달하는 공통 proxy 헬퍼.
export async function proxyJson(
  path: string,
  init: { method: "GET" | "POST"; body?: unknown },
): Promise<NextResponse> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: init.method,
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
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
