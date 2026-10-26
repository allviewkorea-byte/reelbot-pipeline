"use client"

import { useEffect } from "react"
import { CheckCircle2, ChevronLeft, ChevronRight, Loader2, Trash2, X } from "lucide-react"
import type { Ref } from "./studio-lib"

// 크게 보기 — 사진 클릭은 여기만 연다. 확정 변경은 이 안의 "이 사진으로 바꾸기" 버튼으로만
// (실사용에서 확대하려다 확정이 바뀌는 문제). ←/→ 로 같은 역할 사진을 넘기고 Esc 로 닫는다.

export function Lightbox({ title, refs, index, busy, onIndex, onClose, onConfirm, onDiscard }: {
  title: string
  refs: Ref[]
  index: number
  busy: boolean
  onIndex: (i: number) => void
  onClose: () => void
  onConfirm: (ref: Ref) => void
  onDiscard: (ref: Ref) => void
}) {
  const cur = refs[index]
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
      if (e.key === "ArrowRight" && refs.length > 1) onIndex((index + 1) % refs.length)
      if (e.key === "ArrowLeft" && refs.length > 1) onIndex((index - 1 + refs.length) % refs.length)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [index, refs.length, onClose, onIndex])

  if (!cur) return null
  const confirmed = cur.status === "confirmed"

  return (
    <div role="dialog" aria-modal="true" aria-label={`${title} 크게 보기`} className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 p-4" onClick={onClose}>
      <div className="flex max-h-full w-full max-w-lg min-w-0 flex-col gap-3 rounded-xl border border-border bg-card p-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-semibold text-foreground">
            {title}
            {refs.length > 1 && <span className="ml-2 text-xs font-normal text-muted-foreground">{index + 1} / {refs.length}</span>}
          </p>
          <button onClick={onClose} aria-label="닫기" className="rounded-md p-1 text-muted-foreground hover:text-foreground"><X className="h-5 w-5" /></button>
        </div>

        <div className="relative flex min-h-0 items-center justify-center overflow-hidden rounded-lg bg-secondary/30">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={cur.url} alt={title} className="max-h-[62vh] w-full object-contain" />
          {refs.length > 1 && (
            <>
              <button onClick={() => onIndex((index - 1 + refs.length) % refs.length)} aria-label="이전 사진"
                className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full border border-border bg-background/80 p-1.5 text-foreground hover:border-primary/40">
                <ChevronLeft className="h-5 w-5" />
              </button>
              <button onClick={() => onIndex((index + 1) % refs.length)} aria-label="다음 사진"
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full border border-border bg-background/80 p-1.5 text-foreground hover:border-primary/40">
                <ChevronRight className="h-5 w-5" />
              </button>
            </>
          )}
        </div>

        {refs.length > 1 && (
          <div className="flex min-w-0 gap-1.5 overflow-x-auto pb-1">
            {refs.map((r, i) => (
              <button key={r.id} onClick={() => onIndex(i)} aria-label={`${i + 1}번 사진`}
                className={`relative h-16 w-12 shrink-0 overflow-hidden rounded-md border ${i === index ? "border-primary" : "border-border"}`}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={r.url} alt="" className="h-full w-full object-cover" />
                {r.status === "confirmed" && <CheckCircle2 className="absolute right-0.5 top-0.5 h-3.5 w-3.5 text-emerald-400" />}
              </button>
            ))}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          {confirmed ? (
            <span className="flex items-center gap-1.5 text-sm font-medium text-emerald-400"><CheckCircle2 className="h-4 w-4" /> 지금 쓰는 사진이에요</span>
          ) : (
            <button onClick={() => onConfirm(cur)} disabled={busy}
              className="flex min-h-[44px] flex-1 items-center justify-center gap-1.5 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />} 이 사진으로 바꾸기
            </button>
          )}
          <button onClick={() => onDiscard(cur)} disabled={busy}
            className="ml-auto flex min-h-[44px] items-center gap-1 rounded-lg border border-border px-3 text-xs text-muted-foreground hover:text-red-400 disabled:opacity-50">
            <Trash2 className="h-3.5 w-3.5" /> 지우기
          </button>
        </div>
      </div>
    </div>
  )
}
