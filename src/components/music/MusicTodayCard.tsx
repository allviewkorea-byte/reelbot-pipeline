"use client"

// 오늘의 콘텐츠 — 백곰 ContentCalendar 오늘 슬롯 카드 구조·className 1:1 복제(직접 import 금지).
// 음악 cron 은 매일 1회(오전 10:00) → cap 개수만큼 '자동 제작' 슬롯 카드로 표시.
import Link from "next/link"
import { ChevronDown } from "lucide-react"

export function MusicTodayCard({ isActive, isPublic, dailyCap }: { isActive: boolean; isPublic: boolean; dailyCap: number }) {
  const slots = Array.from({ length: Math.max(1, Math.min(3, dailyCap)) }, (_, i) => i + 1)
  const accent = "#8b5cf6"

  return (
    <div className="rounded-xl border border-border bg-card p-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-foreground">오늘의 콘텐츠</h2>
        <Link
          href="/music/queue"
          className="flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-primary/5"
        >
          전체 보기
          <ChevronDown className="h-3.5 w-3.5" />
        </Link>
      </div>

      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
        {slots.map((n) => {
          const cardCls = isActive ? "border-border/60 hover:bg-secondary/30" : "border-dashed border-border/50 opacity-70"
          const statusCls = isActive ? "text-muted-foreground" : "text-muted-foreground/60"
          return (
            <div
              key={n}
              className={`flex min-h-[52px] flex-col gap-1 rounded-lg border p-2.5 text-left transition-colors ${cardCls}`}
            >
              <div className="flex items-center justify-between gap-1">
                <span className="text-xs font-medium text-foreground">
                  자동 제작 {dailyCap > 1 ? `#${n}` : ""}
                  <span className="ml-1 text-[10px] font-normal text-muted-foreground">오전 10시</span>
                </span>
                <span className={`text-[10px] font-medium ${statusCls}`}>{isActive ? "예정" : "정지"}</span>
              </div>
              <span className="flex items-center gap-1.5 truncate text-xs">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: accent }} />
                <span className="truncate font-medium" style={{ color: accent }}>트렌드 가중 주제</span>
                <span className="ml-auto shrink-0 font-mono text-[10px] text-muted-foreground">
                  {isPublic ? "공개" : "검토"}
                </span>
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
