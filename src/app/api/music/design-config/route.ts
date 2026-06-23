import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 디자인 설정(#35-A) — FastAPI /api/music/design-config 프록시.
// GET → 저장값(없으면 기본값) + presets. POST { play_list, where_label } → 저장.
export const dynamic = "force-dynamic"

export async function GET() {
  return proxyJson("/api/music/design-config", { method: "GET" })
}

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}))
  return proxyJson("/api/music/design-config", { method: "POST", body })
}
