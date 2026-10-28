"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { ChevronDown } from "lucide-react"

// 매일 점검 카드(2026-10-28, A 방식) — 매일 09:30 릴봇이 스스로 점검한 결과 + 유튜브 성과.
// compact: 음악 화면 상단용(한 줄 + 펼치기). 기본: 시스템 화면용(전부 펼침).

interface Issue { title: string; cause: string; suggestion: string }
interface YtChannel {
  videos: number; total_views: number; views_gain_1d: number; avg_view_pct: number | null
  top_recent: { title: string; views: number; avg_view_pct: number | null }[]
  bottom_recent: { title: string; views: number; avg_view_pct: number | null }[]
  by_genre: Record<string, number>
}
interface Report {
  date: string; created_at: string
  summary: { level: "ok" | "warn" | "error"; headline: string; issues: Issue[]; good: string[]; source?: string }
  youtube: { channels?: Record<string, YtChannel>; status?: { channels?: Record<string, { stats: string; retention: string }> } }
}

const CH_NAME: Record<string, string> = { workout_music: "2주안에몸매만들기", rooftop_music: "where" }
const DOT = { ok: "bg-emerald-400", warn: "bg-amber-400", error: "bg-red-400" }

export function DailyReportCard({ compact = false }: { compact?: boolean }) {
  const [report, setReport] = useState<Report | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [open, setOpen] = useState(!compact)

  useEffect(() => {
    fetch("/api/system/daily-report", { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => setReport(d?.report ?? null))
      .catch(() => {})
      .finally(() => setLoaded(true))
  }, [])

  if (!loaded) return null
  if (!report) {
    return compact ? null : (
      <div className="rounded-xl border border-border bg-card p-4 text-sm text-muted-foreground">
        아직 매일 점검 기록이 없어요 — 매일 오전 9시 30분에 자동으로 점검해요.
      </div>
    )
  }
  const s = report.summary
  const yt = report.youtube?.channels ?? {}
  const ytStatus = report.youtube?.status?.channels ?? {}
  const needReauth = Object.entries(ytStatus).filter(([, v]) => v.retention.includes("재연결")).map(([k]) => CH_NAME[k] ?? k)

  return (
    <section className="flex min-w-0 flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <button type="button" onClick={() => setOpen((v) => !v)} className="flex min-w-0 items-center gap-2 text-left">
        <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${DOT[s.level] ?? DOT.warn}`} />
        <span className="shrink-0 text-sm font-semibold text-foreground">오늘의 점검</span>
        <span className="min-w-0 truncate text-sm text-muted-foreground">{s.headline}</span>
        <span className="ml-auto shrink-0 text-[11px] text-muted-foreground">{report.date}</span>
        <ChevronDown className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="flex min-w-0 flex-col gap-3">
          {s.issues.length > 0 && (
            <ul className="flex flex-col gap-2">
              {s.issues.map((it, i) => (
                <li key={i} className="rounded-lg border border-border bg-background p-2.5 text-xs">
                  <p className="font-medium text-foreground">{it.title}</p>
                  {it.cause && <p className="mt-0.5 text-muted-foreground">원인: {it.cause}</p>}
                  {it.suggestion && <p className="mt-0.5 text-primary">할 일: {it.suggestion}</p>}
                </li>
              ))}
            </ul>
          )}
          {s.good.length > 0 && <p className="text-xs text-emerald-400">잘 된 점: {s.good.join(" · ")}</p>}

          {Object.keys(yt).length > 0 && (
            <div className="grid min-w-0 gap-2 sm:grid-cols-2">
              {Object.entries(yt).map(([ch, v]) => (
                <div key={ch} className="flex min-w-0 flex-col gap-1 rounded-lg border border-border bg-background p-2.5 text-xs">
                  <p className="font-medium text-foreground">{CH_NAME[ch] ?? ch} · 유튜브 성과</p>
                  <p className="text-muted-foreground">
                    어제보다 조회수 +{v.views_gain_1d.toLocaleString("ko-KR")} · 최근 영상 {v.videos}개
                    {v.avg_view_pct != null && <> · 평균 시청 {v.avg_view_pct}%</>}
                  </p>
                  {v.top_recent[0] && (
                    <p className="truncate text-muted-foreground">
                      최근 1위: {v.top_recent[0].title} ({v.top_recent[0].views.toLocaleString("ko-KR")}회)
                    </p>
                  )}
                  {Object.keys(v.by_genre).length > 1 && (
                    <p className="truncate text-muted-foreground">
                      장르별 평균: {Object.entries(v.by_genre).sort((a, b) => b[1] - a[1]).map(([g, n]) => `${g} ${n.toLocaleString("ko-KR")}`).join(" · ")}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
          {needReauth.length > 0 && (
            <p className="text-xs text-amber-400">
              시청 지속률을 보려면 {needReauth.join(", ")} 채널을 <Link href="/music/settings" className="underline">유튜브 다시 연결</Link>해 주세요.
            </p>
          )}
        </div>
      )}
    </section>
  )
}
