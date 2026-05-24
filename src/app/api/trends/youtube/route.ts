import { NextRequest, NextResponse } from "next/server"
import { fetchTrending, fetchCategories, type TrendItem } from "@/lib/youtube"

// GET /api/trends/youtube?category=<id>&region=KR[&categories=1]
//  - category 비면 지역 전체 인기 영상
//  - categories=1 이면 assignable 카테고리 목록도 함께 반환(셀렉터 초기 로드용, +1 unit)
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const category = searchParams.get("category") ?? ""
  const region = searchParams.get("region") || "KR"
  const withCategories = searchParams.get("categories") === "1"

  try {
    const items = await fetchTrending(category, region)
    const shorts = items.filter((i) => i.format === "shorts")
    const longform = items.filter((i) => i.format === "longform")

    const payload: {
      success: true
      region: string
      category: string
      counts: { shorts: number; longform: number; total: number }
      items: { shorts: TrendItem[]; longform: TrendItem[] }
      categories?: Awaited<ReturnType<typeof fetchCategories>>
    } = {
      success: true,
      region,
      category,
      counts: { shorts: shorts.length, longform: longform.length, total: items.length },
      items: { shorts, longform },
    }

    if (withCategories) {
      payload.categories = await fetchCategories(region)
    }

    return NextResponse.json(payload)
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    // 쿼터/키 오류는 클라이언트가 구분할 수 있도록 메시지를 그대로 전달.
    const status = msg.includes("쿼터") ? 429 : msg.includes("YOUTUBE_API_KEY") ? 500 : 502
    return NextResponse.json({ success: false, error: msg }, { status })
  }
}
