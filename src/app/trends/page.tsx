"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { RefreshCw, Loader2, Clock, Wand2, Hash } from "lucide-react"
import { useChannels } from "@/components/channels/ChannelProvider"
import { SentimentChart } from "@/components/trends/SentimentChart"
import {
  fetchInsights,
  triggerAnalyze,
  saveTrendSettings,
  trendId,
  FORMAT_LABEL,
} from "@/lib/trends"
import type { TrendInsight, TrendSettings } from "@/types/trend"

const DEFAULT_SETTINGS: TrendSettings = {
  enabled: false,
  keywords: [],
  categories: [],
  formats: ["shorts", "long"],
  schedule: "daily",
}

function fmtDate(iso: string): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return "—"
  return d.toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function TagGroup({ label, tags }: { label: string; tags: string[] }) {
  if (!tags.length) return null
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60">
        {label}
      </span>
      <div className="flex flex-wrap gap-1">
        {tags.slice(0, 6).map((t) => (
          <span
            key={t}
            className="rounded-md bg-secondary/50 px-1.5 py-0.5 text-[11px] text-muted-foreground"
          >
            #{t.replace(/^#/, "")}
          </span>
        ))}
      </div>
    </div>
  )
}

function InsightCard({
  insight,
  onMakeScenario,
}: {
  insight: TrendInsight
  onMakeScenario: (i: TrendInsight) => void
}) {
  const tags = insight.tagsByCategory
  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-card p-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-foreground truncate">{insight.category}</p>
          <p className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground">
            <Clock className="h-3 w-3" />
            {fmtDate(insight.analyzedAt)} 갱신
          </p>
        </div>
        <span className="shrink-0 rounded-full bg-secondary/60 px-2 py-0.5 text-xs font-medium text-muted-foreground">
          {FORMAT_LABEL[insight.format]}
        </span>
      </div>

      {/* 권장 길이 / 제목 길이 */}
      <div className="grid grid-cols-2 gap-2 rounded-lg border border-border/60 bg-background/40 p-3 text-center">
        <div>
          <p className="text-xs text-muted-foreground">권장 영상 길이</p>
          <p className="mt-0.5 text-sm font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
            {insight.avgVideoLengthSec ? `${Math.round(insight.avgVideoLengthSec)}초` : "—"}
          </p>
        </div>
        <div className="border-l border-border/60">
          <p className="text-xs text-muted-foreground">권장 제목 길이</p>
          <p className="mt-0.5 text-sm font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
            {insight.avgTitleLength ? `${Math.round(insight.avgTitleLength)}자` : "—"}
          </p>
        </div>
      </div>

      {/* Power Words */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[11px] font-medium text-muted-foreground">Power Words TOP 5</span>
        {insight.powerWords.length ? (
          <div className="flex flex-wrap gap-1.5">
            {insight.powerWords.slice(0, 5).map((p) => (
              <span
                key={p.word}
                className="rounded-full border border-primary/30 bg-primary/10 px-2 py-0.5 text-[11px] text-primary"
              >
                {p.word} <span className="text-primary/60">{p.count}</span>
              </span>
            ))}
          </div>
        ) : (
          <span className="text-[11px] text-muted-foreground/60">데이터 없음</span>
        )}
      </div>

      {/* 추천 해시태그 (5분류, 텍스트 라벨) */}
      <div className="flex flex-col gap-2">
        <span className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground">
          <Hash className="h-3 w-3" /> 추천 해시태그
        </span>
        <TagGroup label="주요" tags={tags.primary} />
        <TagGroup label="변형" tags={tags.variants} />
        <TagGroup label="경쟁" tags={tags.competitor} />
        <TagGroup label="광범위" tags={tags.broad} />
        <TagGroup label="세부" tags={tags.niche} />
      </div>

      {/* 댓글 인사이트 — 감정 도넛 */}
      <div className="flex flex-col gap-1.5">
        <span className="text-[11px] font-medium text-muted-foreground">댓글 감정 분석</span>
        <SentimentChart sentiment={insight.commentInsights.sentiment} />
      </div>

      {/* CTA */}
      <button
        onClick={() => onMakeScenario(insight)}
        className="flex items-center justify-center gap-1.5 rounded-lg bg-primary py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
      >
        <Wand2 className="h-4 w-4" />이 인사이트로 시나리오 만들기
      </button>
    </div>
  )
}

export default function TrendsPage() {
  const router = useRouter()
  const { channels, hydrated, getChannel, updateStack } = useChannels()
  const [channelId, setChannelId] = useState<string>("")
  const [insights, setInsights] = useState<TrendInsight[]>([])
  const [loading, setLoading] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)

  // 채널 목록 로드 후 첫 채널 자동 선택
  useEffect(() => {
    if (!channelId && channels.length) setChannelId(channels[0].id)
  }, [channels, channelId])

  const channel = channelId ? getChannel(channelId) : undefined
  const settings: TrendSettings = useMemo(
    () => ({ ...DEFAULT_SETTINGS, ...(channel?.stack.trendSettings ?? {}) }),
    [channel],
  )

  const load = useCallback(async (cid: string) => {
    if (!cid) return
    setLoading(true)
    try {
      setInsights(await fetchInsights(cid))
    } catch {
      setInsights([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (channelId) load(channelId)
  }, [channelId, load])

  async function pollJob(jobId: string): Promise<void> {
    for (let i = 0; i < 150; i++) {
      await new Promise((r) => setTimeout(r, 2000))
      const res = await fetch(`/api/jobs/${jobId}/status`, { cache: "no-store" })
      const data = await res.json()
      if (data.status === "completed") return
      if (data.status === "failed") throw new Error(data.error || "분석 실패")
    }
    throw new Error("분석 시간이 초과되었습니다")
  }

  async function handleRefresh() {
    if (!channel) return
    if (!settings.categories.length || !settings.keywords.length) {
      toast.error("먼저 채널 설정에서 분석 키워드·카테고리를 지정해주세요")
      router.push(`/channels/${channel.id}`)
      return
    }
    setAnalyzing(true)
    try {
      const { jobId } = await triggerAnalyze({
        channelId: channel.id,
        keywords: settings.keywords,
        categories: settings.categories,
        formats: settings.formats,
      })
      await pollJob(jobId)
      toast.success("트렌드 분석을 갱신했습니다")
      await load(channel.id)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "분석에 실패했습니다")
    } finally {
      setAnalyzing(false)
    }
  }

  async function toggleAuto() {
    if (!channel) return
    const next: TrendSettings = { ...settings, enabled: !settings.enabled }
    updateStack(channel.id, { trendSettings: next })
    try {
      await saveTrendSettings(channel.id, next)
      toast.success(next.enabled ? "자동 갱신을 켰습니다" : "자동 갱신을 껐습니다")
    } catch {
      toast.error("자동 갱신 설정 저장에 실패했습니다")
    }
  }

  function makeScenario(insight: TrendInsight) {
    router.push(`/scenario?trendId=${encodeURIComponent(trendId(insight))}`)
  }

  return (
    <div className="flex flex-1 flex-col gap-6 overflow-auto p-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-foreground">트렌드 분석</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            인기 영상 데이터로 SEO 최적화 인사이트를 카테고리·형식별로 정리합니다
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={channelId}
            onChange={(e) => setChannelId(e.target.value)}
            className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary/50"
          >
            {channels.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>

          <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={settings.enabled}
              onChange={toggleAuto}
              className="h-4 w-4 accent-emerald-600"
            />
            자동 갱신
          </label>

          <button
            onClick={handleRefresh}
            disabled={analyzing || !channel}
            className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {analyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            {analyzing ? "갱신 중…" : "지금 갱신"}
          </button>
        </div>
      </div>

      {/* Body */}
      {!hydrated ? (
        <div className="flex flex-1 items-center justify-center py-16 text-sm text-muted-foreground">
          불러오는 중…
        </div>
      ) : loading ? (
        <div className="flex flex-1 items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> 인사이트를 불러오는 중…
        </div>
      ) : insights.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border py-16 text-center text-sm text-muted-foreground">
          <p>아직 분석된 트렌드가 없습니다.</p>
          <p className="text-xs text-muted-foreground/60">
            채널 설정에서 키워드·카테고리를 지정한 뒤 “지금 갱신”을 눌러보세요.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {insights.map((i) => (
            <InsightCard key={trendId(i)} insight={i} onMakeScenario={makeScenario} />
          ))}
        </div>
      )}
    </div>
  )
}
