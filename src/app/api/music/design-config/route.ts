import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 디자인 설정(#35-A) — FastAPI /api/music/design-config 프록시.
// GET → 저장값(없으면 기본값) + presets. POST { play_list, where_label } → 저장.
//
// 채널별 디자인: 디자인 본부 화면(src/app/music/design/page.tsx, 불변파일)은 채널 없이
// fetch("/api/music/design-config") 만 부른다. 그래서 채널은 ① 요청 쿼리 ?channel= →
// ② 없으면 그 화면 주소(Referer)의 ?channel= 순으로 정한다. 운동 화면의 "디자인 본부"
// 링크는 withChannel 로 ?channel=workout_music 을 달고 간다. 둘 다 없으면 채널을 넘기지
// 않는다 → 백엔드가 where 로 처리(현행 동작 그대로).
export const dynamic = "force-dynamic"

function designPath(request: NextRequest): string {
  let channel = request.nextUrl.searchParams.get("channel") || ""
  if (!channel) {
    const referer = request.headers.get("referer")
    if (referer) {
      try {
        channel = new URL(referer).searchParams.get("channel") || ""
      } catch {
        /* 잘못된 Referer — 채널 없음(where) */
      }
    }
  }
  const qs = channel ? `?channel=${encodeURIComponent(channel)}` : ""
  return `/api/music/design-config${qs}`
}

export async function GET(request: NextRequest) {
  return proxyJson(designPath(request), { method: "GET" })
}

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}))
  return proxyJson(designPath(request), { method: "POST", body })
}
