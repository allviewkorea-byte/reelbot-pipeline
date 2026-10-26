import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/studio/import-shorts { channel, role } — 쇼츠 캐스트 1명을 스튜디오로 복사(원본 cast/… 무변경).
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}))
  return proxyJson("/studio/import-shorts", { method: "POST", body })
}
