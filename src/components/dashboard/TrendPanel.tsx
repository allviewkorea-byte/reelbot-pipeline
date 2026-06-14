"use client"

import { useEffect, useState } from "react"
import { ChevronDown, ChevronUp, Loader2, TrendingUp } from "lucide-react"
import { BAEKGOM_CHANNEL_ID, conceptColor } from "@/lib/content-plan"
import type { TrendRankingItem } from "@/lib/trend-concepts"

// 트렌드 분석(7a-2) — /api/trends/concepts 의 9컨셉 랭킹을 막대그래프로 시각화.
// 접힘=TOP5 컴팩트, 펼침=9컨셉 전체 + 샘플 제목. 컨셉색은 content-plan.ts 재사용.
// ⚠️ 가짜/더미 데이터 없음 — 데이터 없으면 빈 상태 텍스트. 펼침 상태는 page 소유(#117).

// share(0~1) 막대 — 길이는 최댓값 대비 정규화(상위가 꽉 차게), 색은 컨셉색.
function ConceptBar({ item, maxShare, detailed }: { item: TrendRankingItem; maxShare: number; detailed: boolean }) {
  const color = conceptColor(item.concept)
  const width = maxShare > 0 ? Math.max(4, (item.share / maxShare) * 100) : 0
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <span className="flex w-16 shrink-0 items-center gap-1 truncate text-xs font-medium" style={{ color }}>
          <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: color }} />
          {item.concept}
        </span>
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-secondary/40">
          <div className="h-full rounded-full" style={{ width: `${width}%`, backgroundColor: color }} />
        </div>
        <span className="w-9 shrink-0 text-right text-[11px] tabular-nums text-muted-foreground">
          {Math.round(item.share * 100)}%
        </span>
      </div>
      {detailed && (item.sampleTitles.length > 0 || item.reason) && (
        <div className="pl-[4.5rem] pr-11">
          {item.reason && <p className="truncate text-[11px] text-muted-foreground/80">{item.reason}</p>}
          {item.sampleTitles.slice(0, 2).map((t, i) => (
            <p key={i} className="truncate text-[11px] text-muted-foreground/60">· {t}</p>
          ))}
        </div>
      )}
    </div>
  )
}

export function TrendPanel({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const [loading, setLoading] = useState(true)
  const [rankings, setRankings] = useState<TrendRankingItem[]>([])
  const [meta, setMeta] = useState<{ channels: number; videos: number } | null>(null)
  const [date, setDate] = useState("")
  const [error, setError] = useState(false)

  // 마운트 시 1회 로드. 캐시는 API 가 하루 1회로 관리. setState 는 콜백에서만.
  useEffect(() => {
    let alive = true
    fetch(`/api/trends/concepts?channelId=${BAEKGOM_CHANNEL_ID}`)
      .then((r) => r.json())
      .then((d) => {
        if (!alive) return
        if (d?.success && Array.isArray(d.rankings)) {
          setRankings(d.rankings as TrendRankingItem[])
          setMeta(d.meta && typeof d.meta === "object" ? d.meta : null)
          setDate(typeof d.date === "string" ? d.date : "")
        } else {
          setError(true)
        }
      })
      .catch(() => {
        if (alive) setError(true)
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [])

  const hasData = rankings.length > 0
  const maxShare = hasData ? rankings[0].share : 0
  const shown = open ? rankings : rankings.slice(0, 5)

  return (
    <div className="rounded-xl border border-border bg-card p-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
          트렌드 분석
          {loading && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
        </h2>
        <button
          onClick={onToggle}
          aria-expanded={open}
          className="flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-primary/5"
        >
          {open ? "접기" : "전체 보기"}
          {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
      </div>

      {/* 분석 메타 — '진짜 분석했다'는 근거. meta 있으면 채널·영상 수, 없으면(캐시 응답엔
          meta 미포함) 날짜만이라도 표시. 가짜 숫자는 절대 넣지 않음. */}
      {hasData && (meta || date) && (
        <p className="mt-1 text-[11px] text-muted-foreground">
          {meta
            ? open
              ? `채널 ${meta.channels}개 · 영상 ${meta.videos}개 분석${date ? ` · ${date}` : ""}`
              : `최근 ${meta.videos}개 영상 분석${date ? ` · ${date}` : ""}`
            : `분석일 ${date}`}
        </p>
      )}

      {/* 본문 — 로딩/빈상태/막대그래프 */}
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
            {shown.map((item) => (
              <ConceptBar key={item.concept} item={item} maxShare={maxShare} detailed={open} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
