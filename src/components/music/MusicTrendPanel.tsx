"use client"

// 음악 트렌드 분석 — 백곰 TrendPanel(ConceptBar) 구조·className 1:1 복제(직접 import 금지).
// /api/music/trends 의 mood_keywords + hot_situations 를 14장르(SSOT)로 분류 → 빈도 % 가로 막대.
import { useEffect, useState } from "react"
import Link from "next/link"
import { ChevronDown, Loader2, TrendingUp } from "lucide-react"
import { MUSIC_GENRES } from "@/lib/music-genres"

interface TrendInsight {
  analyzed_at?: string
  mood_keywords?: string[]
  hot_situations?: string[]
  summary?: string
}

interface Bar {
  label: string
  color: string
  share: number
}

function classify(trend: TrendInsight): Bar[] {
  const signals = [...(trend.mood_keywords ?? []), ...(trend.hot_situations ?? [])].map((s) => String(s).toLowerCase())
  const counts = MUSIC_GENRES.map((c) => ({
    ...c,
    n: signals.filter((s) => c.keywords.some((k) => s.includes(k.toLowerCase()))).length,
  }))
  const total = counts.reduce((a, c) => a + c.n, 0)
  if (total === 0) return []
  return counts
    .filter((c) => c.n > 0)
    .map((c) => ({ label: c.label, color: c.color, share: c.n / total }))
    .sort((a, b) => b.share - a.share)
}

function ConceptBar({ bar, maxShare }: { bar: Bar; maxShare: number }) {
  const width = maxShare > 0 ? Math.max(4, (bar.share / maxShare) * 100) : 0
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <span className="flex w-16 shrink-0 items-center gap-1 truncate text-xs font-medium" style={{ color: bar.color }}>
          <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: bar.color }} />
          {bar.label}
        </span>
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-secondary/40">
          <div className="h-full rounded-full" style={{ width: `${width}%`, backgroundColor: bar.color }} />
        </div>
        <span className="w-9 shrink-0 text-right text-[11px] tabular-nums text-muted-foreground">
          {Math.round(bar.share * 100)}%
        </span>
      </div>
    </div>
  )
}

export function MusicTrendPanel() {
  const [loading, setLoading] = useState(true)
  const [trend, setTrend] = useState<TrendInsight | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let alive = true
    fetch("/api/music/trends")
      .then((r) => r.json())
      .then((d) => {
        if (!alive) return
        setTrend(d?.trend ?? null)
      })
      .catch(() => alive && setError(true))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [])

  const bars = trend ? classify(trend) : []
  const hasData = bars.length > 0
  const maxShare = hasData ? bars[0].share : 0
  const date = trend?.analyzed_at ? new Date(trend.analyzed_at).toLocaleDateString("ko-KR") : ""

  return (
    <div className="rounded-xl border border-border bg-card p-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
          트렌드 분석
          {loading && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
        </h2>
        <Link
          href="/music/guide"
          className="flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-primary/5"
        >
          전체 보기
          <ChevronDown className="h-3.5 w-3.5" />
        </Link>
      </div>

      {hasData && (date || trend?.summary) && (
        <p className="mt-1 truncate text-[11px] text-muted-foreground">
          {trend?.summary ? trend.summary : `분석일 ${date}`}
        </p>
      )}

      <div className="mt-2">
        {loading ? (
          <p className="py-6 text-center text-xs text-muted-foreground">트렌드 분석 중…</p>
        ) : !hasData ? (
          <div className="flex flex-col items-center justify-center gap-1 rounded-lg border border-dashed border-border/60 px-4 py-6 text-center">
            <TrendingUp className="h-5 w-5 text-muted-foreground/50" />
            <p className="text-xs text-muted-foreground">
              {error ? "트렌드 데이터를 불러오지 못했습니다." : "표시할 트렌드 데이터가 없습니다."}
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {bars.map((b) => (
              <ConceptBar key={b.label} bar={b} maxShare={maxShare} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
