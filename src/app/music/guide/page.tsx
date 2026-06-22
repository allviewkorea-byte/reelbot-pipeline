"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { ArrowLeft, Loader2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"

interface RecentTheme {
  slug: string
  title_kr?: string
  genre?: string
  mood?: string
  situation?: string
}

export default function MusicGuidePage() {
  const [palette, setPalette] = useState<string[]>([])
  const [recent, setRecent] = useState<RecentTheme[]>([])
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
  }, [])

  return (
    <div className="flex h-full min-h-0 flex-col gap-6 overflow-auto p-4 md:p-6">
      <header className="flex items-center gap-3">
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
