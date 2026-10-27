import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// POST /api/insta/collections/plan { character_id, n } — 컬렉션 릴스 미리보기(테마·장면·상품, 이미지 생성 없음).
export const dynamic = "force-dynamic"

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}))
  return proxyJson("/insta/collections/plan", { method: "POST", body })
}
