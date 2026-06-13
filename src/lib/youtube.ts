// 서버 전용 YouTube Data API v3 어댑터 (wavespeed.ts 와 동일한 어댑터 패턴).
//
// 쿼터 주의: videoCategories.list / videos.list 는 각 1 unit, 일일 10,000 limit.
// search.list(호출당 100 unit)는 사용하지 않는다. 쇼츠 구분은 API 필터가 없으므로
// contentDetails.duration 을 파싱해 분류한다.

import type { MarqueeVideo } from "@/components/dashboard/RecentVideosMarquee"

const YT_BASE = "https://www.googleapis.com/youtube/v3"

export type VideoFormatKind = "shorts" | "longform"

// PR 2(시나리오 자동 연결)가 입력으로 받는 공개 인터페이스.
export interface TrendItem {
  id: string
  title: string
  channelTitle: string
  publishedAt: string
  thumbnail: string
  viewCount: number
  likeCount: number
  commentCount: number
  durationSec: number
  format: VideoFormatKind
}

export interface YoutubeCategory {
  id: string
  title: string
}

// ── 내부 응답 타입(필요 필드만) ─────────────────────────────────────
interface RawCategory {
  id: string
  snippet?: { title?: string; assignable?: boolean }
}
interface RawVideo {
  id: string
  snippet?: {
    title?: string
    channelTitle?: string
    publishedAt?: string
    thumbnails?: Record<string, { url?: string } | undefined>
  }
  contentDetails?: { duration?: string }
  statistics?: { viewCount?: string; likeCount?: string; commentCount?: string }
}
interface YtListResponse<T> {
  items?: T[]
}
interface YtErrorBody {
  error?: { message?: string; errors?: Array<{ reason?: string }> }
}

function getApiKey(): string {
  const key = process.env.YOUTUBE_API_KEY
  if (!key) {
    throw new Error("YOUTUBE_API_KEY가 설정되지 않았습니다 (.env.local · 서버 전용)")
  }
  return key
}

async function ytFetch<T>(path: string, params: Record<string, string | number>): Promise<T> {
  const url = new URL(`${YT_BASE}${path}`)
  url.searchParams.set("key", getApiKey())
  for (const [k, v] of Object.entries(params)) {
    url.searchParams.set(k, String(v))
  }

  const res = await fetch(url.toString())
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as YtErrorBody | null
    const reason = body?.error?.errors?.[0]?.reason
    const message = body?.error?.message ?? res.statusText

    if (res.status === 403 && (reason === "quotaExceeded" || reason === "dailyLimitExceeded")) {
      throw new Error("YouTube API 일일 쿼터를 초과했습니다. 잠시 후 다시 시도하세요.")
    }
    if (reason === "keyInvalid" || reason === "badRequest") {
      throw new Error("YOUTUBE_API_KEY가 유효하지 않습니다. 키 설정을 확인하세요.")
    }
    throw new Error(`YouTube API 오류 (${res.status}): ${message}`)
  }
  return res.json() as Promise<T>
}

// assignable=true 인 카테고리만 반환 (사용자가 영상에 지정 가능한 카테고리).
export async function fetchCategories(regionCode = "KR"): Promise<YoutubeCategory[]> {
  const data = await ytFetch<YtListResponse<RawCategory>>("/videoCategories", {
    part: "snippet",
    regionCode,
  })
  return (data.items ?? [])
    .filter((it) => it.snippet?.assignable)
    .map((it) => ({ id: it.id, title: it.snippet?.title ?? "(제목 없음)" }))
}

// ISO 8601 duration("PT1M30S") → 초 단위 숫자.
export function parseDuration(iso8601: string): number {
  const m = /^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/.exec(iso8601 ?? "")
  if (!m) return 0
  const [, h, min, s] = m
  return (Number(h) || 0) * 3600 + (Number(min) || 0) * 60 + (Number(s) || 0)
}

// 180초 이하는 쇼츠, 그 외는 롱폼으로 분류.
export function classifyFormat(durationSec: number): VideoFormatKind {
  return durationSec <= 180 ? "shorts" : "longform"
}

// chart=mostPopular 인기 영상. categoryId 가 비면 지역 전체 인기 영상을 받는다.
// 일부 카테고리는 mostPopular 결과가 없을 수 있으므로 빈 배열을 graceful 하게 반환한다.
export async function fetchTrending(categoryId: string, regionCode = "KR"): Promise<TrendItem[]> {
  const params: Record<string, string | number> = {
    part: "snippet,contentDetails,statistics",
    chart: "mostPopular",
    maxResults: 50,
    regionCode,
  }
  if (categoryId) params.videoCategoryId = categoryId

  const data = await ytFetch<YtListResponse<RawVideo>>("/videos", params)
  return (data.items ?? []).map((it) => {
    const durationSec = parseDuration(it.contentDetails?.duration ?? "")
    const thumbs = it.snippet?.thumbnails ?? {}
    const thumbnail = thumbs.medium?.url ?? thumbs.high?.url ?? thumbs.default?.url ?? ""
    return {
      id: it.id,
      title: it.snippet?.title ?? "",
      channelTitle: it.snippet?.channelTitle ?? "",
      publishedAt: it.snippet?.publishedAt ?? "",
      thumbnail,
      viewCount: Number(it.statistics?.viewCount ?? 0),
      likeCount: Number(it.statistics?.likeCount ?? 0),
      commentCount: Number(it.statistics?.commentCount ?? 0),
      durationSec,
      format: classifyFormat(durationSec),
    }
  })
}

// 큰 수를 컴팩트 표기로(5100→"5.1K", 12000→"12K", 88→"88"). 더미 표기와 일관.
function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, "")}K`
  return String(n)
}

// 채널의 '공개' 업로드 영상을 마퀴용 MarqueeVideo[] 로 반환(서버 전용, API 키).
// 흐름: channels.list(uploads 재생목록) → playlistItems.list(videoId) →
// videos.list(snippet,statistics,status). status.privacyStatus==="public" 만 노출
// (비공개는 키 조회 시 자동 제외 + 명시 필터). 쿼터 3 unit/호출. 실패는 호출부에서 처리.
export async function fetchChannelUploads(channelId: string, max = 10): Promise<MarqueeVideo[]> {
  if (!channelId) return []

  // 1) 업로드 재생목록 id
  const ch = await ytFetch<
    YtListResponse<{ contentDetails?: { relatedPlaylists?: { uploads?: string } } }>
  >("/channels", { part: "contentDetails", id: channelId })
  const uploads = ch.items?.[0]?.contentDetails?.relatedPlaylists?.uploads
  if (!uploads) return []

  // 2) 재생목록 → videoId 목록
  const pl = await ytFetch<YtListResponse<{ contentDetails?: { videoId?: string } }>>(
    "/playlistItems",
    { part: "contentDetails", playlistId: uploads, maxResults: max },
  )
  const ids = (pl.items ?? [])
    .map((i) => i.contentDetails?.videoId)
    .filter((v): v is string => Boolean(v))
  if (ids.length === 0) return []

  // 3) 영상 상세(공개 영상만)
  const vids = await ytFetch<YtListResponse<RawVideo & { status?: { privacyStatus?: string } }>>(
    "/videos",
    { part: "snippet,statistics,status", id: ids.join(",") },
  )
  return (vids.items ?? [])
    .filter((v) => v.status?.privacyStatus === "public")
    .map((v) => {
      const thumbs = v.snippet?.thumbnails ?? {}
      const thumbnailUrl =
        thumbs.medium?.url ?? thumbs.high?.url ?? thumbs.default?.url ?? ""
      return {
        id: v.id,
        platform: "youtube" as const,
        title: v.snippet?.title ?? "",
        thumbnailUrl,
        viewCount: `조회 ${formatCount(Number(v.statistics?.viewCount ?? 0))}`,
        commentCount: `댓글 ${formatCount(Number(v.statistics?.commentCount ?? 0))}`,
        videoUrl: `https://www.youtube.com/watch?v=${v.id}`,
      }
    })
}
