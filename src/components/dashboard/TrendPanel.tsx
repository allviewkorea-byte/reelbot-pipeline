"use client"

import { ChevronDown, ChevronUp, TrendingUp } from "lucide-react"

// 트렌드 분석 — '빈 그릇'(준비 중)만. 실제 컨셉 트렌드 엔진은 다음 PR 에서 이 그릇에 연결.
// ⚠️ 가짜 랭킹·더미 숫자 절대 없음. 펼쳐도 "준비 중" 안내만 표시한다.
// 펼침 상태는 상위(page)가 소유 — 월간 계획서와 짝으로 동시 펼침/접힘(controlled).
export function TrendPanel({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  return (
    <div className="rounded-xl border border-border bg-card p-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
          트렌드 분석
          <span className="rounded-full bg-secondary/50 px-2 py-0.5 text-[11px] font-normal text-muted-foreground">
            준비 중
          </span>
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

      {open && (
        <div className="mt-3 flex flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed border-border/60 px-4 py-8 text-center">
          <TrendingUp className="h-6 w-6 text-muted-foreground/50" />
          <p className="text-sm font-medium text-muted-foreground">트렌드 분석 준비 중</p>
          <p className="text-xs text-muted-foreground/70">곧 유튜브 컨셉 트렌드가 여기에 표시됩니다.</p>
        </div>
      )}
    </div>
  )
}
