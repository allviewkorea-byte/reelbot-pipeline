"use client"

import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts"

// 차트 색은 디자인 시스템의 --chart-1~3 토큰을 호출. 미정의 환경에서는
// 기존 팔레트(보라/시안/주황) 값으로 fallback — 새 색을 정의하지 않는다.
const CHART_COLORS = {
  positive: "hsl(var(--chart-1, 265 89% 66%))",
  neutral: "hsl(var(--chart-2, 188 86% 43%))",
  negative: "hsl(var(--chart-3, 38 92% 50%))",
}

const LABELS: Record<string, string> = {
  positive: "긍정",
  neutral: "중립",
  negative: "부정",
}

interface Sentiment {
  positive: number
  negative: number
  neutral: number
}

function pct(n: number): string {
  return `${Math.round(n * 100)}%`
}

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: { name: string; value: number }[]
}) {
  if (!active || !payload?.length) return null
  const p = payload[0]
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 shadow-lg">
      <p className="text-xs text-muted-foreground">{LABELS[p.name] ?? p.name}</p>
      <p
        className="text-sm font-bold text-foreground"
        style={{ fontFamily: "var(--font-geist-mono)" }}
      >
        {pct(p.value)}
      </p>
    </div>
  )
}

export function SentimentChart({ sentiment }: { sentiment: Sentiment }) {
  const data = [
    { name: "positive", value: sentiment.positive },
    { name: "neutral", value: sentiment.neutral },
    { name: "negative", value: sentiment.negative },
  ]
  const hasData = data.some((d) => d.value > 0)

  if (!hasData) {
    return (
      <p className="py-4 text-center text-xs text-muted-foreground/60">
        댓글 데이터 없음
      </p>
    )
  }

  return (
    <div className="flex items-center gap-4">
      <div className="h-[120px] w-[120px] shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              innerRadius={32}
              outerRadius={54}
              paddingAngle={2}
              stroke="none"
            >
              {data.map((entry) => (
                <Cell
                  key={entry.name}
                  fill={CHART_COLORS[entry.name as keyof typeof CHART_COLORS]}
                />
              ))}
            </Pie>
            <Tooltip content={<ChartTooltip />} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="flex flex-col gap-1.5">
        {data.map((entry) => (
          <div key={entry.name} className="flex items-center gap-2">
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: CHART_COLORS[entry.name as keyof typeof CHART_COLORS] }}
            />
            <span className="text-xs text-muted-foreground">{LABELS[entry.name]}</span>
            <span
              className="text-xs font-bold text-foreground"
              style={{ fontFamily: "var(--font-geist-mono)" }}
            >
              {pct(entry.value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
