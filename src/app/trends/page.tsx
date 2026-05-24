"use client"

import { useCallback, useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Loader2, RefreshCw, Sparkles, Eye, ThumbsUp, MessageSquare, ExternalLink, Wand2, Hash, Clock, Save } from "lucide-react"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { TrendItem, YoutubeCategory, VideoFormatKind } from "@/lib/youtube"

interface Analysis {
  summary: string
  commonThemes: string[]
  formatTraits: string[]
  scenarioHints: string[]
}

interface ScenarioSuggestion {
  titles: string[]
  description: string
  hashtags: {
    category: string[]
    topic: string[]
    emotion: string[]
    target: string[]
    trend: string[]
  }
  duration: { format: VideoFormatKind; minutes: number }
}

const HASHTAG_GROUPS: { key: keyof ScenarioSuggestion["hashtags"]; label: string }[] = [
  { key: "category", label: "카테고리" },
  { key: "topic", label: "주제" },
  { key: "emotion", label: "감성" },
  { key: "target", label: "타겟" },
  { key: "trend", label: "트렌드" },
]

interface TrendData {
  shorts: TrendItem[]
  longform: TrendItem[]
}

const FORMAT_LABEL: Record<VideoFormatKind, string> = {
  shorts: "쇼츠",
  longform: "롱폼",
}

function formatCount(n: number): string {
  if (n >= 1e8) return `${(n / 1e8).toFixed(1).replace(/\.0$/, "")}억`
  if (n >= 1e4) return `${(n / 1e4).toFixed(1).replace(/\.0$/, "")}만`
  return n.toLocaleString("ko-KR")
}

function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}:${String(s).padStart(2, "0")}`
}

function engagementRate(it: TrendItem): string {
  if (!it.viewCount) return "—"
  const rate = ((it.likeCount + it.commentCount) / it.viewCount) * 100
  return `${rate.toFixed(1)}%`
}

function TrendCard({ item }: { item: TrendItem }) {
  return (
    <a
      href={`https://www.youtube.com/watch?v=${item.id}`}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex flex-col overflow-hidden rounded-xl border border-border bg-card transition-colors hover:border-primary/40"
    >
      <div className="relative aspect-video w-full overflow-hidden bg-secondary/40">
        {item.thumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={item.thumbnail}
            alt={item.title}
            className="h-full w-full object-cover transition-transform group-hover:scale-105"
            referrerPolicy="no-referrer"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
            썸네일 없음
          </div>
        )}
        <span className="absolute bottom-1.5 right-1.5 rounded bg-black/70 px-1.5 py-0.5 text-[10px] font-medium text-white">
          {formatDuration(item.durationSec)}
        </span>
      </div>

      <div className="flex flex-1 flex-col gap-2 p-3">
        <p className="line-clamp-2 text-sm font-medium text-foreground" title={item.title}>
          {item.title}
        </p>
        <p className="truncate text-xs text-muted-foreground">{item.channelTitle}</p>

        <div className="mt-auto flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <Eye className="h-3 w-3 text-primary" />
            {formatCount(item.viewCount)}
          </span>
          <span className="flex items-center gap-1">
            <ThumbsUp className="h-3 w-3 text-cyan-400" />
            {formatCount(item.likeCount)}
          </span>
          <span className="flex items-center gap-1">
            <MessageSquare className="h-3 w-3 text-amber-400" />
            {formatCount(item.commentCount)}
          </span>
          <span className="ml-auto rounded-full bg-secondary/60 px-2 py-0.5 font-medium text-foreground">
            참여율 {engagementRate(item)}
          </span>
        </div>
      </div>
    </a>
  )
}

function InsightBlock({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-xs font-semibold text-foreground">{title}</p>
      <ul className="flex flex-col gap-1">
        {items.map((t, i) => (
          <li key={i} className="flex gap-1.5 text-xs text-muted-foreground">
            <span className="text-primary">•</span>
            <span>{t}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function TrendsPage() {
  const router = useRouter()
  const [categories, setCategories] = useState<YoutubeCategory[]>([])
  const [categoryId, setCategoryId] = useState<string>("")
  const [format, setFormat] = useState<VideoFormatKind>("shorts")
  const [data, setData] = useState<TrendData>({ shorts: [], longform: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string>("")

  const [analyzing, setAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)

  const [suggesting, setSuggesting] = useState(false)
  const [suggestion, setSuggestion] = useState<ScenarioSuggestion | null>(null)
  const [selectedTitle, setSelectedTitle] = useState<string | null>(null)

  const loadTrends = useCallback(async (cid: string, withCategories: boolean) => {
    setLoading(true)
    setError("")
    setAnalysis(null)
    setSuggestion(null)
    setSelectedTitle(null)
    try {
      const params = new URLSearchParams({ region: "KR" })
      if (cid) params.set("category", cid)
      if (withCategories) params.set("categories", "1")
      const res = await fetch(`/api/trends/youtube?${params.toString()}`, { cache: "no-store" })
      const json = await res.json()
      if (!res.ok || !json.success) throw new Error(json.error || "트렌드를 불러오지 못했습니다")
      setData(json.items)
      if (withCategories && Array.isArray(json.categories)) {
        setCategories(json.categories)
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "트렌드를 불러오지 못했습니다"
      setError(msg)
      setData({ shorts: [], longform: [] })
    } finally {
      setLoading(false)
    }
  }, [])

  // 최초 로드: 전체 인기 영상 + 카테고리 목록.
  // setState 가 effect 본문에서 동기 호출되지 않도록 마이크로태스크로 미룬다.
  useEffect(() => {
    void Promise.resolve().then(() => loadTrends("", true))
  }, [loadTrends])

  function onCategoryChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const cid = e.target.value
    setCategoryId(cid)
    loadTrends(cid, false)
  }

  const currentItems = data[format]
  const categoryTitle = categories.find((c) => c.id === categoryId)?.title ?? "전체"

  async function analyze() {
    if (!currentItems.length) {
      toast.error("분석할 영상이 없습니다")
      return
    }
    setAnalyzing(true)
    setSuggestion(null)
    setSelectedTitle(null)
    try {
      const res = await fetch("/api/trends/youtube/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          items: currentItems,
          category: categoryTitle,
          format,
        }),
      })
      const json = await res.json()
      if (!res.ok || !json.success) throw new Error(json.error || "AI 분석에 실패했습니다")
      setAnalysis(json.analysis)
      toast.success("AI 분석을 완료했습니다")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "AI 분석에 실패했습니다")
    } finally {
      setAnalyzing(false)
    }
  }

  // AI 인사이트 → 시나리오 초안 생성.
  async function makeScenario() {
    if (!analysis) return
    setSuggesting(true)
    setSuggestion(null)
    setSelectedTitle(null)
    try {
      const res = await fetch("/api/trends/scenario", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ insights: analysis, category: categoryTitle, format }),
      })
      const json = await res.json()
      if (!res.ok || !json.success) throw new Error(json.error || "시나리오 생성에 실패했습니다")
      const next = json.suggestion as ScenarioSuggestion
      setSuggestion(next)
      setSelectedTitle(next.titles[0] ?? null)
      toast.success("시나리오 초안을 만들었습니다")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "시나리오 생성에 실패했습니다")
    } finally {
      setSuggesting(false)
    }
  }

  // 시나리오 초안을 기존 핸드오프 패턴(sessionStorage)으로 /scenario 생성 폼에 전달.
  function saveToScenario() {
    if (!suggestion) return
    const title = selectedTitle || suggestion.titles[0] || ""
    const fmt = suggestion.duration.format === "shorts" ? "short" : "long"
    const minutes = Math.max(1, Math.round(suggestion.duration.minutes))
    const params = {
      category: categoryTitle,
      tone: "밝고 경쾌",
      format: fmt,
      durationMin: minutes,
      sceneCount: Math.max(6, minutes * 6),
      modelCount: "1인",
      topic: title,
    }
    try {
      sessionStorage.setItem("reelbot:scenarioParams", JSON.stringify(params))
    } catch {
      /* sessionStorage 사용 불가 시에도 이동은 진행 */
    }
    toast.success("시나리오 보관함으로 전달했습니다")
    router.push("/scenario")
  }

  return (
    <div className="flex flex-1 flex-col gap-6 overflow-auto p-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-foreground">트렌드 분석</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            YouTube 인기 영상을 카테고리·형식별로 살펴보고 AI 인사이트를 받아보세요 (지역: 한국)
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={categoryId}
            onChange={onCategoryChange}
            disabled={loading}
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary/50 disabled:opacity-50"
          >
            <option value="">전체 인기</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </select>

          <button
            onClick={() => loadTrends(categoryId, categories.length === 0)}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm font-medium text-foreground transition-colors hover:border-primary/40 disabled:opacity-50"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            새로고침
          </button>

          <button
            onClick={analyze}
            disabled={analyzing || loading || !currentItems.length}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {analyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            {analyzing ? "분석 중…" : "AI 분석"}
          </button>
        </div>
      </div>

      {/* 형식 토글 */}
      <Tabs value={format} onValueChange={(v) => setFormat(v as VideoFormatKind)}>
        <TabsList>
          <TabsTrigger value="shorts">
            {FORMAT_LABEL.shorts}
            <span className="ml-1.5 text-xs opacity-70">{data.shorts.length}</span>
          </TabsTrigger>
          <TabsTrigger value="longform">
            {FORMAT_LABEL.longform}
            <span className="ml-1.5 text-xs opacity-70">{data.longform.length}</span>
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {/* AI 인사이트 패널 */}
      {analysis && (
        <div className="flex flex-col gap-4 rounded-xl border border-primary/30 bg-primary/5 p-5">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold text-foreground">AI 인사이트</h2>
            <span className="rounded-full bg-secondary/60 px-2 py-0.5 text-xs text-muted-foreground">
              {FORMAT_LABEL[format]} · {categoryTitle}
            </span>
          </div>
          {analysis.summary && <p className="text-sm text-muted-foreground">{analysis.summary}</p>}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <InsightBlock title="공통 주제" items={analysis.commonThemes} />
            <InsightBlock title="포맷 특징" items={analysis.formatTraits} />
            <InsightBlock title="시나리오 힌트" items={analysis.scenarioHints} />
          </div>
          {/* 인사이트 → 시나리오 초안 생성 */}
          <div className="flex justify-end border-t border-primary/20 pt-3">
            <button
              onClick={makeScenario}
              disabled={suggesting}
              className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700 disabled:opacity-50"
            >
              {suggesting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
              {suggesting ? "생성 중…" : "시나리오 만들기"}
            </button>
          </div>
        </div>
      )}

      {/* 시나리오 초안 패널 */}
      {suggestion && (
        <div className="flex flex-col gap-5 rounded-xl border border-emerald-600/30 bg-card p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
              <Wand2 className="h-4 w-4 text-emerald-500" />
              시나리오 초안
            </h2>
            <span className="flex items-center gap-1 rounded-full bg-secondary/60 px-2 py-0.5 text-xs font-medium text-muted-foreground">
              <Clock className="h-3 w-3" />
              {FORMAT_LABEL[suggestion.duration.format]} · 약 {suggestion.duration.minutes}분
            </span>
          </div>

          {/* 제목 후보 — 클릭해 선택 */}
          <div>
            <p className="mb-2 text-xs font-medium text-muted-foreground">
              제목 후보 <span className="text-muted-foreground/60">(클릭해 선택)</span>
            </p>
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              {suggestion.titles.map((title) => {
                const active = selectedTitle === title
                return (
                  <button
                    key={title}
                    onClick={() => setSelectedTitle(title)}
                    className={`flex items-start gap-2 rounded-lg border p-3 text-left text-xs transition-all ${
                      active
                        ? "border-primary/50 bg-primary/10 text-foreground"
                        : "border-border bg-background text-muted-foreground hover:border-primary/30 hover:text-foreground"
                    }`}
                  >
                    <span
                      className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 ${
                        active ? "border-primary" : "border-muted-foreground/40"
                      }`}
                    >
                      {active && <span className="h-2 w-2 rounded-full bg-primary" />}
                    </span>
                    <span className="flex-1">{title}</span>
                  </button>
                )
              })}
            </div>
          </div>

          {/* 설명 미리보기 */}
          <div>
            <p className="mb-1.5 text-xs font-medium text-muted-foreground">
              설명 미리보기 <span className="text-muted-foreground/60">(첫 150자: 후크 → 핵심 → CTA)</span>
            </p>
            <p className="rounded-lg border border-border bg-background px-3 py-2 text-xs leading-relaxed text-foreground">
              {suggestion.description || "—"}
            </p>
          </div>

          {/* 해시태그 5분류 */}
          <div>
            <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Hash className="h-3.5 w-3.5" /> 해시태그 5분류
            </p>
            <div className="flex flex-col gap-2">
              {HASHTAG_GROUPS.map(({ key, label }) => {
                const tags = suggestion.hashtags[key]
                if (!tags.length) return null
                return (
                  <div key={key} className="flex flex-wrap items-center gap-1.5">
                    <span className="w-12 shrink-0 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60">
                      {label}
                    </span>
                    {tags.map((t) => (
                      <span
                        key={t}
                        className="rounded-md bg-secondary/50 px-1.5 py-0.5 text-[11px] text-muted-foreground"
                      >
                        #{t.replace(/^#/, "")}
                      </span>
                    ))}
                  </div>
                )
              })}
            </div>
          </div>

          {/* 보관함 저장 */}
          <div className="flex justify-end border-t border-border pt-3">
            <button
              onClick={saveToScenario}
              className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700"
            >
              <Save className="h-4 w-4" />
              시나리오 보관함에 저장
            </button>
          </div>
        </div>
      )}

      {/* 결과 그리드 */}
      {loading ? (
        <div className="flex flex-1 items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> 인기 영상을 불러오는 중…
        </div>
      ) : error ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border py-16 text-center text-sm text-muted-foreground">
          <p className="text-foreground">{error}</p>
          <button onClick={() => loadTrends(categoryId, categories.length === 0)} className="text-xs text-primary hover:underline">
            다시 시도
          </button>
        </div>
      ) : currentItems.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border py-16 text-center text-sm text-muted-foreground">
          <p>이 카테고리·형식에는 인기 영상 데이터가 없습니다.</p>
          <p className="text-xs text-muted-foreground/60">다른 카테고리나 형식을 선택해보세요.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {currentItems.map((item) => (
            <TrendCard key={item.id} item={item} />
          ))}
        </div>
      )}

      {/* 외부 링크 안내 */}
      {!loading && !error && currentItems.length > 0 && (
        <p className="flex items-center gap-1 text-xs text-muted-foreground/60">
          <ExternalLink className="h-3 w-3" /> 카드를 클릭하면 YouTube에서 원본 영상을 엽니다
        </p>
      )}
    </div>
  )
}
