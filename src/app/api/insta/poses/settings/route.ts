import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/insta/poses/settings { enabled?, cats?, angles?, excluded? } — 포즈 참고 설정 저장.
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}))
  return proxyJson("/insta/poses/settings", { method: "POST", body })
}
