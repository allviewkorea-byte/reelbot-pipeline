import type { TrendInsight, TrendSettings, VideoFormat } from "@/types/trend"

// ── API 헬퍼 (Next proxy 경유 → FastAPI) ─────────────────────────────

export async function fetchInsights(
  channelId: string,
  category?: string,
  format?: VideoFormat,
): Promise<TrendInsight[]> {
  const qs = new URLSearchParams()
  if (category) qs.set("category", category)
  if (format) qs.set("format", format)
  const suffix = qs.toString() ? `?${qs.toString()}` : ""
  const res = await fetch(`/api/trends/${encodeURIComponent(channelId)}${suffix}`, {
    cache: "no-store",
  })
  if (!res.ok) return []
  const data = await res.json()
  return (data.insights ?? []) as TrendInsight[]
}

export async function triggerAnalyze(payload: {
  channelId: string
  keywords: string[]
  categories: string[]
  formats: VideoFormat[]
}): Promise<{ jobId: string }> {
  const res = await fetch("/api/trends/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || data.error || "분석 요청 실패")
  return { jobId: data.job_id }
}

export async function saveTrendSettings(
  channelId: string,
  settings: TrendSettings,
): Promise<void> {
  const res = await fetch(`/api/channels/${encodeURIComponent(channelId)}/trend-settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || data.error || "설정 저장 실패")
  }
}

// ── 시나리오 자동 생성 헬퍼 ──────────────────────────────────────────

export const FORMAT_LABEL: Record<VideoFormat, string> = {
  shorts: "쇼츠",
  long: "롱폼",
}

// 시나리오 생성과 동일한 9개 카테고리.
export const TREND_CATEGORIES = [
  "여행",
  "음식·맛집",
  "라이프스타일",
  "패션·뷰티",
  "교육·정보",
  "유머·엔터테인먼트",
  "동기부여",
  "일상",
  "비즈니스",
] as const

export function trendId(insight: Pick<TrendInsight, "channelId" | "category" | "format">): string {
  return `${insight.channelId}__${insight.category}__${insight.format}`
}

export function parseTrendId(
  id: string,
): { channelId: string; category: string; format: VideoFormat } | null {
  const parts = id.split("__")
  if (parts.length !== 3) return null
  const [channelId, category, format] = parts
  if (format !== "shorts" && format !== "long") return null
  return { channelId, category, format }
}

/** Power Words 를 끼워넣은 제목 후보 3~5개 생성. */
export function buildTitleCandidates(insight: TrendInsight, topic: string): string[] {
  const subject = topic.trim() || insight.category
  const words = insight.powerWords.map((p) => p.word).filter(Boolean)
  const primary = insight.tagsByCategory.primary[0] ?? insight.category

  const templates = [
    (w: string) => `${w} ${subject}, 이건 꼭 보세요`,
    (w: string) => `${subject} ${w} 총정리`,
    (w: string) => `아무도 몰랐던 ${subject}의 ${w} 포인트`,
    (w: string) => `${primary} | ${w} ${subject} 가이드`,
    (w: string) => `${subject}, ${w}하게 즐기는 법`,
  ]

  const seeds = words.length ? words : ["완벽", "꿀팁", "최고", "추천", "필수"]
  const candidates: string[] = []
  for (let i = 0; i < templates.length && candidates.length < 5; i++) {
    const w = seeds[i % seeds.length]
    const title = templates[i](w)
    if (!candidates.includes(title)) candidates.push(title)
  }
  return candidates.slice(0, 5)
}

/** 첫 150자 키워드 + 후크 구조로 설명 자동 생성. */
export function buildDescription(insight: TrendInsight, topic: string): string {
  const subject = topic.trim() || insight.category
  const kws = insight.descriptionPattern.first150Keywords.slice(0, 6)
  const hook = insight.descriptionPattern.hookStructure
  const hookLine = hook ? `${hook} ` : ""
  const kwLine = kws.length ? `${subject} | ${kws.join(", ")}` : subject
  return `${hookLine}${kwLine}`.slice(0, 150)
}

/** 5분류 해시태그를 합쳐 # 접두 문자열 배열로 반환. */
export function combineHashtags(insight: TrendInsight): string[] {
  const t = insight.tagsByCategory
  const all = [...t.primary, ...t.variants, ...t.broad, ...t.niche, ...t.competitor]
  const seen = new Set<string>()
  const out: string[] = []
  for (const tag of all) {
    const clean = tag.replace(/^#/, "").trim()
    if (clean && !seen.has(clean)) {
      seen.add(clean)
      out.push(`#${clean}`)
    }
  }
  return out.slice(0, 15)
}

/** 형식별 권장 영상 길이(초)를 분 단위로 변환. */
export function recommendDurationMin(insight: TrendInsight): number {
  const sec = insight.avgVideoLengthSec
  if (!sec || sec <= 0) return insight.format === "shorts" ? 1 : 4
  return Math.max(1, Math.round(sec / 60))
}
