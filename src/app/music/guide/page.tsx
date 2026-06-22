"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { ArrowLeft, Loader2, TrendingUp } from "lucide-react"
import { Badge } from "@/components/ui/badge"

interface RecentTheme {
  slug: string
  title_kr?: string
  genre?: string
  mood?: string
  situation?: string
}

interface TrendInsight {
  analyzed_at?: string
  mood_keywords?: string[]
  title_patterns?: string[]
  hot_situations?: string[]
  summary?: string
  raw_samples?: { title: string; view_count: number; channel?: string }[]
}

function fmtViews(n: number): string {
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}억`
  if (n >= 10_000) return `${(n / 10_000).toFixed(1)}만`
  return n.toLocaleString("ko-KR")
}

export default function MusicGuidePage() {
  const [palette, setPalette] = useState<string[]>([])
  const [recent, setRecent] = useState<RecentTheme[]>([])
  const [trend, setTrend] = useState<TrendInsight | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch("/api/music/themes")
      .then((r) => r.json())
      .then((d) => {
        setPalette(Array.isArray(d?.palette) ? d.palette : [])
        setRecent(Array.isArray(d?.recent) ? d.recent : [])
      })
      .catch(() => {
        /* 빈 상태 유지 */
      })
      .finally(() => setLoading(false))
    fetch("/api/music/trends")
      .then((r) => r.json())
      .then((d) => setTrend(d?.trend ?? null))
      .catch(() => {
        /* 트렌드 없으면 섹션 숨김 */
      })
  }, [])

  return (
    <div className="flex h-full min-h-0 flex-col gap-6 overflow-auto p-4 md:p-6">
      <header className="flex items-center gap-3 pl-10 md:pl-0">
        <Link
          href="/music"
          className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground hover:bg-white/5 hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> 큐로
        </Link>
        <div>
          <h1 className="text-xl font-semibold text-foreground">테마 가이드</h1>
          <p className="text-sm text-muted-foreground">채널 장르 팔레트 + 최근 생성 주제(읽기 전용)</p>
        </div>
      </header>

      {/* 요즘 트렌드 — 영감용 인사이트(있을 때만) */}
      {trend && (trend.summary || (trend.mood_keywords?.length ?? 0) > 0) && (
        <section className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
          <div className="flex items-center justify-between gap-2">
            <h2 className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
              <TrendingUp className="h-4 w-4 text-primary" /> 요즘 트렌드
            </h2>
            {trend.analyzed_at && (
              <span className="text-xs text-muted-foreground">
                분석: {new Date(trend.analyzed_at).toLocaleDateString("ko-KR")}
              </span>
            )}
          </div>
          {trend.summary && (
            <p className="text-sm leading-relaxed text-foreground/90">💡 {trend.summary}</p>
          )}
          {(trend.mood_keywords?.length ?? 0) > 0 && (
            <div className="flex flex-col gap-1.5">
              <span className="text-xs text-muted-foreground">뜨는 무드</span>
              <div className="flex flex-wrap gap-1.5">
                {trend.mood_keywords!.map((m) => (
                  <Badge key={m} variant="secondary">{m}</Badge>
                ))}
              </div>
            </div>
          )}
          {(trend.hot_situations?.length ?? 0) > 0 && (
            <div className="flex flex-col gap-1.5">
              <span className="text-xs text-muted-foreground">인기 상황</span>
              <div className="flex flex-wrap gap-1.5">
                {trend.hot_situations!.map((s) => (
                  <Badge key={s} variant="outline">{s}</Badge>
                ))}
              </div>
            </div>
          )}
          {(trend.raw_samples?.length ?? 0) > 0 && (
            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">참고 인기 영상</span>
              <ul className="flex flex-col gap-1">
                {trend.raw_samples!.slice(0, 5).map((v, i) => (
                  <li key={i} className="flex items-center justify-between gap-2 text-xs text-foreground/80">
                    <span className="truncate">{v.title}</span>
                    <span className="shrink-0 font-mono text-muted-foreground">{fmtViews(v.view_count)}회</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-[11px] text-muted-foreground/70">
            ※ 영감용 — 특정 주제를 강제하지 않고 무드·톤 방향성으로만 반영됩니다.
          </p>
        </section>
      )}

      {/* 장르 팔레트 */}
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium uppercase tracking-wider text-muted-foreground">장르 팔레트</h2>
        <div className="flex flex-wrap gap-2">
          {palette.map((g) => (
            <Badge key={g} variant="secondary" className="text-sm">
              {g}
            </Badge>
          ))}
        </div>
      </section>

      {/* 최근 주제 10개 */}
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium uppercase tracking-wider text-muted-foreground">최근 생성 주제</h2>
        {loading ? (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" /> 불러오는 중…
          </div>
        ) : recent.length === 0 ? (
          <p className="text-sm text-muted-foreground">아직 생성된 주제가 없습니다.</p>
        ) : (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {recent.map((t) => (
              <div key={t.slug} className="flex flex-col gap-1.5 rounded-lg border border-border bg-card p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium text-foreground">{t.title_kr || t.slug}</span>
                  <span className="shrink-0 font-mono text-xs text-muted-foreground">{t.slug}</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {t.genre && <Badge variant="outline">{t.genre}</Badge>}
                  {t.mood && <Badge variant="outline">{t.mood}</Badge>}
                  {t.situation && <Badge variant="outline">{t.situation}</Badge>}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
