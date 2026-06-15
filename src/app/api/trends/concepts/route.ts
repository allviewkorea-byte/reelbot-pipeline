import { NextRequest, NextResponse } from "next/server"
import { resolveChannelId, fetchChannelVideoStats } from "@/lib/youtube"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"
import { getTrendRanking, saveTrendRanking } from "@/lib/supabase"
import { classifyWithGPT } from "@/lib/trend-classify-gpt"
import {
  buildRankings,
  classifyByKeywords,
  todayKST,
  TREND_SOURCE_CHANNELS,
  TREND_PER_CHANNEL_MAX,
  TREND_TOTAL_MAX,
  type ClassifyInput,
  type TrendRankingItem,
  type TrendSource,
} from "@/lib/trend-concepts"

// 트렌드 컨셉 엔진(7a-1): 유튜브 인기 숏폼 → GPT(폴백 키워드)로 사연 9컨셉 분류 →
// 조회수 가중 랭킹 → Supabase 캐시 → JSON 반환. 화면 표시(패널)는 7a-2.
// (GPT 분류는 lib/trend-classify-gpt 로 추출 — cron finalize 와 공유. 동작 동일.)
//
// 매 요청마다 외부(YouTube/OpenAI)·DB 를 타므로 정적 캐시 금지(동적 라우트).
export const dynamic = "force-dynamic"


// GET /api/trends/concepts?channelId= — 오늘 캐시 있으면 반환, 없으면 수집·분류·저장 후 반환.
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const channelId = searchParams.get("channelId") || BAEKGOM_CHANNEL_ID
  const date = todayKST()

  // 1) 캐시(하루 1회) — 같은 날 재호출은 쿼터·비용 절약.
  const cached = await getTrendRanking(channelId, date)
  if (cached) {
    return NextResponse.json({
      success: true,
      cached: true,
      date,
      source: cached.source,
      rankings: cached.rankings ?? [],
    })
  }

  // 2) 지정 사연 채널들의 최근 영상 수집(전부 사연 → 9컨셉 분산). 핸들→ID 변환.
  //    채널당 실패는 건너뛰고(전체 안 깨짐), 최근순 정렬 후 전체 상한 적용.
  const collected: { title: string; viewCount: number; publishedAt: string }[] = []
  let analyzedChannels = 0
  for (const ref of TREND_SOURCE_CHANNELS) {
    try {
      const id = await resolveChannelId(ref)
      if (!id) {
        console.warn(`[trends/concepts] 채널 ID 변환 실패 — 건너뜀: ${ref}`)
        continue
      }
      const vids = await fetchChannelVideoStats(id, TREND_PER_CHANNEL_MAX)
      if (vids.length > 0) {
        analyzedChannels++
        for (const v of vids) {
          collected.push({ title: v.title, viewCount: v.viewCount, publishedAt: v.publishedAt })
        }
      }
    } catch (e) {
      console.warn(`[trends/concepts] 채널 수집 실패 — 건너뜀: ${ref}`, e instanceof Error ? e.message : e)
    }
  }
  // 최근순 정렬 후 전체 상한(토큰·비용 관리).
  collected.sort((a, b) => (b.publishedAt || "").localeCompare(a.publishedAt || ""))
  const inputs: ClassifyInput[] = collected
    .slice(0, TREND_TOTAL_MAX)
    .map((c) => ({ title: c.title, viewCount: c.viewCount }))

  if (inputs.length === 0) {
    // 수집 실패(키 없음 등) → 빈 랭킹(앱 안 깨짐). 캐시에 저장하지 않아 다음에 재시도.
    return NextResponse.json({
      success: true,
      cached: false,
      date,
      source: "empty",
      rankings: [],
      meta: { channels: analyzedChannels, videos: 0 },
    })
  }

  // 3) 분류: GPT 메인 → 실패 시 키워드 룰 폴백.
  let source: TrendSource = "gpt"
  let rankings: TrendRankingItem[]
  const gpt = await classifyWithGPT(inputs)
  if (gpt) {
    rankings = buildRankings(gpt.classified, gpt.reasons)
  } else {
    source = "keyword"
    rankings = buildRankings(classifyByKeywords(inputs))
  }

  // 4) 캐시 저장(베스트 에포트 — 테이블 미존재 등으로 실패해도 결과는 반환).
  try {
    await saveTrendRanking({ id: `${channelId}_${date}`, channel_id: channelId, date, source, rankings })
  } catch {
    /* 저장 실패해도 결과 반환 */
  }

  return NextResponse.json({
    success: true,
    cached: false,
    date,
    source,
    rankings,
    meta: { channels: analyzedChannels, videos: inputs.length },
  })
}
