"use client"

import { useState } from "react"
import { toast } from "sonner"
import { Loader2, AlertTriangle, RotateCcw, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { JOB_TYPE_LABEL, STEP_LABEL, STEP_NODE_INDEX, relTime, type MusicJob } from "@/lib/music-jobs"

// 검토대기 상단 진행/실패 카드(#36) — 페이지 이동·기기 전환에도 DB 기준으로 유지.
const cardBase = "flex flex-col gap-2 rounded-xl border bg-card p-3 shadow-sm"

// 파이프라인과 동일한 6단계 라벨(주제·음원·가사·영상·합성·업로드).
const NODE_LABELS = ["주제", "음원", "가사", "영상", "합성", "업로드"]

export function MusicJobCard({ job, onChanged }: { job: MusicJob; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)
  const failed = job.status === "failed"
  const typeLabel = JOB_TYPE_LABEL[job.type] ?? job.type
  const stepLabel = job.step ? STEP_LABEL[job.step] ?? job.step : "준비 중"
  const idx = job.step ? STEP_NODE_INDEX[job.step] ?? 0 : 0

  const dismiss = async () => {
    setBusy(true)
    try {
      const r = await fetch(`/api/music/jobs/${job.job_id}/dismiss`, { method: "POST" })
      if (!r.ok) throw new Error()
      onChanged()
    } catch {
      toast.error("닫기 실패")
    } finally {
      setBusy(false)
    }
  }

  const retry = async () => {
    setBusy(true)
    try {
      const r = await fetch(`/api/music/jobs/${job.job_id}/retry`, { method: "POST" })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(d?.detail || "재시도 실패")
      toast.success("재시도를 시작했습니다.")
      onChanged()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "재시도 실패")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={cn(cardBase, failed ? "border-red-500/40" : "border-primary/30")}>
      <div className="flex items-center gap-2">
        {failed ? (
          <AlertTriangle className="h-4 w-4 shrink-0 text-red-500" />
        ) : (
          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
        )}
        <span className="text-sm font-semibold text-foreground">
          {failed ? `${typeLabel} 실패` : typeLabel}
        </span>
        <span className="ml-auto text-[11px] text-muted-foreground">{relTime(job.created_at)}</span>
      </div>

      {failed ? (
        <p className="text-xs text-muted-foreground">
          단계: <span className="text-foreground/90">{stepLabel}</span>
          {job.error_message ? <><br />원인: <span className="text-red-400">{job.error_message}</span></> : null}
        </p>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            단계: <span className="text-foreground/90">{stepLabel}</span>
          </p>
          {/* 6단계 진행 바(파이프라인과 동일 순서) */}
          <div className="flex flex-wrap items-center gap-1">
            {NODE_LABELS.map((s, i) => (
              <span
                key={s}
                className={cn(
                  "rounded px-1.5 py-0.5 text-[10px] font-medium",
                  i < idx
                    ? "bg-emerald-500/15 text-emerald-400"
                    : i === idx
                      ? "bg-primary/15 text-primary"
                      : "bg-secondary/40 text-muted-foreground",
                )}
              >
                {s}
              </span>
            ))}
          </div>
        </>
      )}

      {failed && (
        <div className="flex items-center gap-2 border-t border-border pt-2">
          {(job.type === "manual_render" || job.type === "rerender") && (
            <button
              type="button"
              onClick={retry}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <RotateCcw className="h-3 w-3" />} 재시도
            </button>
          )}
          <button
            type="button"
            onClick={dismiss}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-xs font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            <X className="h-3 w-3" /> 닫기
          </button>
        </div>
      )}
    </div>
  )
}
