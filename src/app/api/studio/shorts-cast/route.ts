import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// GET /api/studio/shorts-cast?channel= — 쇼츠 캐스트 중 스튜디오로 가져올 수 있는 캐릭터.
export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  const channel = req.nextUrl.searchParams.get("channel") || "workout_music"
  return proxyJson(`/studio/shorts-cast?channel=${encodeURIComponent(channel)}`, { method: "GET" })
}
