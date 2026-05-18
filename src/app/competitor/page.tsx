"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Search, Wand2, TrendingUp, ArrowRight } from "lucide-react"

const INSIGHTS = [
  {
    id: "hook",
    rank: "01",
    title: "오프닝 후크",
    subtitle: "첫 3초 임팩트",
    pct: 87,
    color: "#22c55e",
    colorBg: "bg-emerald-500/15",
    colorText: "text-emerald-400",
    desc: "87% 영상이 충격적 장면으로 시작 → 이탈률 42% 감소",
  },
  {
    id: "mukbang",
    rank: "02",
    title: "먹방 씬 위치",
    subtitle: "영상 40~60% 구간",
    pct: 73,
    color: "#eab308",
    colorBg: "bg-amber-500/15",
    colorText: "text-amber-400",
    desc: "중반부 먹방 삽입 시 시청 지속률 73% 향상",
  },
  {
    id: "length",
    rank: "03",
    title: "영상 길이",
    subtitle: "4~6분 최적",
    pct: 91,
    color: "#3b82f6",
    colorBg: "bg-blue-500/15",
    colorText: "text-blue-400",
    desc: "4~6분 영상이 알고리즘 노출 91% 더 높음",
  },
]

export default function CompetitorPage() {
  const router = useRouter()
  const [url, setUrl] = useState("")
  const [analyzed, setAnalyzed] = useState(true) // show mock results by default

  return (
    <div className="flex flex-1 flex-col gap-6 p-6 overflow-auto">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-foreground">경쟁사 분석</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          인기 채널을 분석해서 콘텐츠 전략을 뽑아냅니다
        </p>
      </div>

      {/* Input card */}
      <div className="rounded-xl border border-border bg-card p-5">
        <label className="mb-2 block text-xs font-medium text-muted-foreground">
          YouTube 채널 URL 입력
        </label>
        <div className="relative mb-4">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://youtube.com/channel/..."
            className="w-full rounded-lg border border-border bg-background py-2.5 pl-10 pr-4 text-sm text-foreground placeholder:text-muted-foreground/50 focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/30"
          />
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setAnalyzed(true)}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg border border-border py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-secondary/40"
          >
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
            분석하기
          </button>
          <button
            onClick={() => setAnalyzed(true)}
            className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90"
          >
            <Wand2 className="h-4 w-4" />
            ✦ AI 자동분석
          </button>
        </div>
      </div>

      {/* Results */}
      {analyzed && (
        <>
          <div>
            <h2 className="text-sm font-semibold text-foreground">
              유사 여행 채널 Top 3 인사이트
            </h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              상위 채널 분석 기반 콘텐츠 전략
            </p>
          </div>

          <div className="flex flex-col gap-3">
            {INSIGHTS.map((ins) => (
              <div
                key={ins.id}
                className="rounded-xl border border-border bg-card p-4"
              >
                <div className="flex items-start gap-4">
                  {/* Rank */}
                  <span
                    className="text-2xl font-bold text-border"
                    style={{ fontFamily: "var(--font-geist-mono)" }}
                  >
                    {ins.rank}
                  </span>

                  <div className="flex-1 min-w-0">
                    {/* Title row */}
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <span className="text-sm font-semibold text-foreground">
                          {ins.title}
                        </span>
                        <span className="ml-2 text-xs text-muted-foreground">
                          — {ins.subtitle}
                        </span>
                      </div>
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${ins.colorBg} ${ins.colorText}`}
                        style={{ fontFamily: "var(--font-geist-mono)" }}
                      >
                        {ins.pct}%
                      </span>
                    </div>

                    {/* Progress bar */}
                    <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-secondary">
                      <div
                        className="h-full rounded-full transition-all"
                        style={{ width: `${ins.pct}%`, backgroundColor: ins.color }}
                      />
                    </div>

                    {/* Description */}
                    <p className="mt-2 text-xs text-muted-foreground">{ins.desc}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* CTA */}
          <div className="rounded-xl border border-primary/20 bg-primary/5 p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-foreground">
                  인사이트 적용 준비 완료
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  3개 전략이 시나리오에 자동 반영됩니다
                </p>
              </div>
              <button
                onClick={() => router.push("/scenario")}
                className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90"
              >
                이 인사이트를 시나리오에 반영
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
