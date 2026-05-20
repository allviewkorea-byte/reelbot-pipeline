"use client"

import { Loader2 } from "lucide-react"
import type { JobStatus } from "@/lib/api"

export function ProgressTracker({
  jobStatus,
  title = "진행 중",
}: {
  jobStatus: JobStatus | null
  title?: string
}) {
  const progress = jobStatus?.progress ?? 0
  const step = jobStatus?.current_step ?? "준비 중…"

  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-4 rounded-xl border border-border bg-card p-8">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
      <div className="w-full text-center">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        <p className="mt-1 text-xs text-muted-foreground">{step}</p>
      </div>

      <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
        <div
          className="h-full rounded-full bg-primary transition-all duration-300"
          style={{ width: `${Math.min(Math.max(progress, 0), 100)}%` }}
        />
      </div>
      <p
        className="text-xs font-bold text-foreground"
        style={{ fontFamily: "var(--font-geist-mono)" }}
      >
        {progress}%
      </p>
    </div>
  )
}
