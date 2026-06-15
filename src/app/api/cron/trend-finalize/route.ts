import { NextRequest, NextResponse } from "next/server"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"
import { listChannelVideos, saveTrendRanking, deleteOldChannelVideos } from "@/lib/supabase"
import { classifyWithGPT } from "@/lib/trend-classify-gpt"
import { isAuthorizedCron } from "@/lib/cron-auth"
import {
  buildRankings,
  classifyByKeywords,
  todayKST,
  FINALIZE_CLASSIFY_MAX,
  type ClassifyInput,
  type RawTrendVideo,
  type TrendRankingItem,
  type TrendSource,
} from "@/lib/trend-concepts"

// 7c: 오늘(KST) 채널별 부분결과를 모아 GPT(폴백 키워드) 분류 → 랭킹 → trend_rankings 저장.
// index 무관 — 그날 있는 partial 전부 합침(채널 추가 시 호출만 늘리면 됨). GPT 1회만.
// 분류는 조회수 상위 FINALIZE_CLASSIFY_MAX 개만 → 출력 토큰↓로 타임아웃 방지.
export const dynamic = "force-dynamic"
// Hobby 함수 60초 허용(기본 10초) — GPT 단계 여유. (가벼워졌지만 안전마진)
export const maxDuration = 60

export async function GET(req: NextRequest) {
  if (!isAuthorizedCron(req)) {
    return NextResponse.json({ success: false, error: "unauthorized" }, { status: 401 })
  }

  const date = todayKST()
  const channelId = BAEKGOM_CHANNEL_ID

  try {
    const rows = await listChannelVideos(channelId, date)
    const channelsWithData = rows.filter((r) => Array.isArray(r.videos) && r.videos.length > 0).length

    // merge → 조회수 상위 정렬 → 분류 상한(타임아웃 방지). 상위 조회수가 share 신호 대부분.
    const merged: RawTrendVideo[] = []
    for (const r of rows) for (const v of r.videos ?? []) merged.push(v)
    merged.sort((a, b) => (b.viewCount || 0) - (a.viewCount || 0))
    const inputs: ClassifyInput[] = merged
      .slice(0, FINALIZE_CLASSIFY_MAX)
      .map((v) => ({ title: v.title, viewCount: v.viewCount }))

    if (inputs.length === 0) {
      // 부분결과 없음(채널 수집 전/실패) → 저장하지 않음(다음 실행에 재시도).
      return NextResponse.json({
        success: true,
        date,
        source: "empty",
        rankings: [],
        meta: { channels: channelsWithData, videos: 0 },
      })
    }

    // 분류: GPT 메인 → 실패 시 키워드 룰 폴백.
    let source: TrendSource = "gpt"
    let rankings: TrendRankingItem[]
    const gpt = await classifyWithGPT(inputs)
    if (gpt) {
      rankings = buildRankings(gpt.classified, gpt.reasons)
    } else {
      source = "keyword"
      rankings = buildRankings(classifyByKeywords(inputs))
    }

    await saveTrendRanking({ id: `${channelId}_${date}`, channel_id: channelId, date, source, rankings })
    // 이전 날짜 partial 정리(오늘 것은 보존 — roll/재실행 대비).
    await deleteOldChannelVideos(channelId, date)

    return NextResponse.json({
      success: true,
      date,
      source,
      rankings,
      meta: { channels: channelsWithData, videos: inputs.length },
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Unknown error"
    return NextResponse.json({ success: false, error: msg }, { status: 500 })
  }
}
