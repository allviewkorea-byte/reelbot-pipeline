import { NextRequest, NextResponse } from "next/server"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"
import { getTrendRanking } from "@/lib/supabase"
import { todayKST } from "@/lib/trend-concepts"
import { buildConceptWeights, pickConcept } from "@/lib/calendar-generate"

// 시작 제작용 컨셉 추첨 — 오늘 trend_rankings 있으면 트렌드 가중 컨셉 1개(7b 로직 재사용),
// 없으면 빈 topic(→ 백엔드 _TOPIC_POOL 랜덤 폴백). 컨셉명을 그대로 topic 으로 쓴다
// (autoscript 가 topic 을 '소재 결'로 사용하므로 매핑표 불필요). 서버 전용(Supabase).
// generate-script 프록시는 건드리지 않는다([자동 생성] 화면 보호 — 트렌드화 X).
export const dynamic = "force-dynamic"

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const channelId = searchParams.get("channelId") || BAEKGOM_CHANNEL_ID
  try {
    const ranking = await getTrendRanking(channelId, todayKST())
    const rankings = ranking?.rankings ?? []
    if (rankings.length > 0) {
      const weights = buildConceptWeights(rankings)
      const topic = pickConcept(weights, new Set<string>(), new Set<string>())
      return NextResponse.json({ success: true, topic, source: "trend" })
    }
    return NextResponse.json({ success: true, topic: "", source: "random" })
  } catch {
    // 실패해도 제작을 막지 않는다 → 빈 topic 폴백(랜덤).
    return NextResponse.json({ success: true, topic: "", source: "random" })
  }
}
