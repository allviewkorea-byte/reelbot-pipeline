"use client"

import { useCallback, useEffect, useMemo, useState, type KeyboardEvent } from "react"
import { ChevronDown, ChevronUp, X, AlertTriangle, Loader2, Trash2 } from "lucide-react"
import {
  BAEKGOM_CHANNEL_ID,
  CONTENT_CONCEPTS,
  CONCEPT_CONFLICT_WINDOW_DAYS,
  type ContentPlan,
  type ContentPlanStatus,
} from "@/lib/content-plan"

const FIELD =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary/50"
const WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
const STATUS_LABEL: Record<ContentPlanStatus, string> = {
  planned: "예정",
  done: "완료",
  skipped: "건너뜀",
}

// ── 날짜 헬퍼(라이브러리 없이) ───────────────────────────────────────
function toISO(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}
function addDays(d: Date, n: number): Date {
  const r = new Date(d)
  r.setDate(r.getDate() + n)
  return r
}
function startOfWeek(d: Date): Date {
  // 월요일 시작
  const r = new Date(d)
  const day = (r.getDay() + 6) % 7 // 월=0 … 일=6
  r.setDate(r.getDate() - day)
  r.setHours(0, 0, 0, 0)
  return r
}
function diffDays(a: string, b: string): number {
  return Math.round((new Date(a).getTime() - new Date(b).getTime()) / 86400000)
}

// 월간 6주 그리드(월요일 시작) 날짜 배열.
function monthGrid(year: number, month: number): Date[] {
  const first = new Date(year, month, 1)
  const start = startOfWeek(first)
  return Array.from({ length: 42 }, (_, i) => addDays(start, i))
}

// 연속 컨셉 감지: 같은 컨셉이 앞뒤 N일 내 다른 날에도 있으면 충돌(plan id 집합).
function detectConflicts(plans: ContentPlan[]): Set<string> {
  const conflict = new Set<string>()
  for (let i = 0; i < plans.length; i++) {
    for (let j = 0; j < plans.length; j++) {
      if (i === j) continue
      const a = plans[i]
      const b = plans[j]
      if (!a.concept || a.concept !== b.concept) continue
      if (Math.abs(diffDays(a.date, b.date)) <= CONCEPT_CONFLICT_WINDOW_DAYS) {
        conflict.add(a.id)
      }
    }
  }
  return conflict
}

export function ContentCalendar() {
  const [today] = useState(() => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return d
  })
  const [monthOpen, setMonthOpen] = useState(false)
  const [viewMonth, setViewMonth] = useState(() => ({ y: today.getFullYear(), m: today.getMonth() }))
  const [plans, setPlans] = useState<ContentPlan[]>([])
  const [loading, setLoading] = useState(true)
  const [editDate, setEditDate] = useState<string | null>(null)

  // 가시 범위(현재 달 ±1주)를 넉넉히 조회 — 주간 스트립 + 월간 그리드 모두 커버.
  const range = useMemo(() => {
    const first = new Date(viewMonth.y, viewMonth.m, 1)
    const last = new Date(viewMonth.y, viewMonth.m + 1, 0)
    return { from: toISO(addDays(first, -7)), to: toISO(addDays(last, 7)) }
  }, [viewMonth])

  // setState 는 비동기 콜백에서만 호출(effect 본문 직접 호출 회피).
  const reload = useCallback(() => {
    fetch(`/api/content-plans?channel=${BAEKGOM_CHANNEL_ID}&from=${range.from}&to=${range.to}`)
      .then((r) => r.json())
      .then((d) => {
        const list = Array.isArray(d?.plans) ? (d.plans as ContentPlan[]) : []
        setPlans(list)
      })
      .catch(() => setPlans([]))
      .finally(() => setLoading(false))
  }, [range.from, range.to])

  useEffect(() => {
    reload()
  }, [reload])

  const byDate = useMemo(() => {
    const m = new Map<string, ContentPlan>()
    for (const p of plans) if (!m.has(p.date)) m.set(p.date, p)
    return m
  }, [plans])
  const conflicts = useMemo(() => detectConflicts(plans), [plans])
  const conflictDates = useMemo(
    () => new Set(plans.filter((p) => conflicts.has(p.id)).map((p) => p.date)),
    [plans, conflicts],
  )

  const weekDates = useMemo(() => {
    const s = startOfWeek(today)
    return Array.from({ length: 7 }, (_, i) => addDays(s, i))
  }, [today])
  const grid = useMemo(() => monthGrid(viewMonth.y, viewMonth.m), [viewMonth])

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          콘텐츠 캘린더
          {loading && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
          {conflictDates.size > 0 && (
            <span className="flex items-center gap-1 text-xs font-normal text-amber-400">
              <AlertTriangle className="h-3.5 w-3.5" />연속 컨셉 {conflictDates.size}건
            </span>
          )}
        </h2>
        <button
          onClick={() => setMonthOpen((v) => !v)}
          className="flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-primary/5"
        >
          {monthOpen ? "주간 보기" : "전체 보기"}
          {monthOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
      </div>

      {/* 주간 스트립 */}
      {!monthOpen && (
        <div className="grid grid-cols-7 gap-2">
          {weekDates.map((d, i) => {
            const iso = toISO(d)
            const plan = byDate.get(iso)
            const isToday = iso === toISO(today)
            return (
              <button
                key={iso}
                onClick={() => setEditDate(iso)}
                className={`flex min-h-[72px] flex-col gap-1 rounded-lg border p-2 text-left transition-colors ${
                  isToday ? "border-primary/50 bg-primary/5" : "border-border/60 hover:bg-secondary/30"
                }`}
              >
                <span className="text-xs text-muted-foreground">
                  {WEEKDAYS[i]} {d.getDate()}
                </span>
                {plan ? (
                  <span className="flex items-center gap-1 truncate text-xs font-medium text-foreground">
                    {conflictDates.has(iso) && <AlertTriangle className="h-3 w-3 shrink-0 text-amber-400" />}
                    {plan.concept}
                  </span>
                ) : (
                  <span className="text-xs text-muted-foreground/50">—</span>
                )}
              </button>
            )
          })}
        </div>
      )}

      {/* 월간 그리드 (전체 보기) — styled-jsx 슬라이드/페이드 */}
      {monthOpen && (
        <div className="month-anim">
          <div className="mb-2 flex items-center justify-between">
            <button
              onClick={() => setViewMonth((v) => (v.m === 0 ? { y: v.y - 1, m: 11 } : { y: v.y, m: v.m - 1 }))}
              className="rounded px-2 py-1 text-sm text-muted-foreground hover:text-foreground"
            >
              ‹
            </button>
            <span className="text-sm font-medium text-foreground">
              {viewMonth.y}년 {viewMonth.m + 1}월
            </span>
            <button
              onClick={() => setViewMonth((v) => (v.m === 11 ? { y: v.y + 1, m: 0 } : { y: v.y, m: v.m + 1 }))}
              className="rounded px-2 py-1 text-sm text-muted-foreground hover:text-foreground"
            >
              ›
            </button>
          </div>
          <div className="mb-1 grid grid-cols-7 gap-1 text-center text-xs text-muted-foreground">
            {WEEKDAYS.map((w) => (
              <span key={w}>{w}</span>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {grid.map((d) => {
              const iso = toISO(d)
              const plan = byDate.get(iso)
              const inMonth = d.getMonth() === viewMonth.m
              const isToday = iso === toISO(today)
              return (
                <button
                  key={iso}
                  onClick={() => setEditDate(iso)}
                  className={`flex min-h-[56px] flex-col gap-0.5 rounded-md border p-1.5 text-left transition-colors ${
                    isToday ? "border-primary/50" : "border-border/40"
                  } ${inMonth ? "hover:bg-secondary/30" : "opacity-40"}`}
                >
                  <span className="text-[11px] text-muted-foreground">{d.getDate()}</span>
                  {plan && (
                    <span className="flex items-center gap-0.5 truncate text-[11px] font-medium text-foreground">
                      {conflictDates.has(iso) && <AlertTriangle className="h-2.5 w-2.5 shrink-0 text-amber-400" />}
                      {plan.concept}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
          <style jsx>{`
            .month-anim {
              animation: slideDown 0.25s ease;
            }
            @keyframes slideDown {
              from {
                opacity: 0;
                transform: translateY(-6px);
              }
              to {
                opacity: 1;
                transform: none;
              }
            }
            @media (prefers-reduced-motion: reduce) {
              .month-anim {
                animation: none;
              }
            }
          `}</style>
        </div>
      )}

      {editDate && (
        <PlanEditor
          date={editDate}
          plan={byDate.get(editDate) ?? null}
          onClose={() => setEditDate(null)}
          onSaved={() => {
            setEditDate(null)
            reload()
          }}
        />
      )}
    </div>
  )
}

function PlanEditor({
  date,
  plan,
  onClose,
  onSaved,
}: {
  date: string
  plan: ContentPlan | null
  onClose: () => void
  onSaved: () => void
}) {
  const [concept, setConcept] = useState(plan?.concept || CONTENT_CONCEPTS[0])
  const [title, setTitle] = useState(plan?.title || "")
  const [memo, setMemo] = useState(plan?.memo || "")
  const [status, setStatus] = useState<ContentPlanStatus>(plan?.status || "planned")
  const [busy, setBusy] = useState(false)

  const save = async () => {
    setBusy(true)
    try {
      const res = await fetch("/api/content-plans", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: plan?.id,
          date,
          concept,
          title: title.trim() || null,
          memo: memo.trim() || null,
          status,
        }),
      })
      if (res.ok) onSaved()
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!plan) return
    setBusy(true)
    try {
      const res = await fetch(`/api/content-plans/${encodeURIComponent(plan.id)}`, { method: "DELETE" })
      if (res.ok) onSaved()
    } finally {
      setBusy(false)
    }
  }

  // Enter=저장(기존 save 재사용). IME 한글 조합 중 Enter 는 무시. 저장 진행 중이면 무시.
  const handleTitleKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== "Enter" || e.nativeEvent.isComposing) return
    e.preventDefault()
    if (!busy) save()
  }
  // 메모: Enter=저장 / Ctrl(Cmd)+Enter=줄바꿈 삽입(일반 textarea 와 반대).
  const handleMemoKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key !== "Enter" || e.nativeEvent.isComposing) return
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault()
      const ta = e.currentTarget
      const start = ta.selectionStart
      const end = ta.selectionEnd
      setMemo(memo.slice(0, start) + "\n" + memo.slice(end))
      requestAnimationFrame(() => {
        ta.selectionStart = ta.selectionEnd = start + 1
      })
      return
    }
    e.preventDefault()
    if (!busy) save()
  }

  // CloneModal 오버레이 패턴 재사용(Sheet/Dialog 없음).
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-base font-semibold text-foreground">{date}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground" aria-label="닫기">
            <X className="h-4 w-4" />
          </button>
        </div>

        <label className="mb-1.5 block text-xs font-medium text-muted-foreground">컨셉</label>
        <div className="mb-4 flex flex-wrap gap-2">
          {CONTENT_CONCEPTS.map((c) => (
            <button
              key={c}
              onClick={() => setConcept(c)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                concept === c
                  ? "bg-primary/20 text-primary border border-primary/30"
                  : "border border-border text-muted-foreground hover:text-foreground"
              }`}
            >
              {c}
            </button>
          ))}
        </div>

        <label className="mb-1.5 block text-xs font-medium text-muted-foreground">제목 (선택)</label>
        <input
          className={`${FIELD} mb-4`}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={handleTitleKey}
          placeholder="예: 남친 집에서 발견한…"
        />

        <label className="mb-1.5 block text-xs font-medium text-muted-foreground">메모 (선택)</label>
        <textarea
          className={`${FIELD} mb-1 min-h-16 resize-y`}
          value={memo}
          onChange={(e) => setMemo(e.target.value)}
          onKeyDown={handleMemoKey}
        />
        <p className="mb-4 text-[11px] text-muted-foreground">Enter 저장 · Ctrl(⌘)+Enter 줄바꿈</p>

        <label className="mb-1.5 block text-xs font-medium text-muted-foreground">상태</label>
        <div className="mb-6 flex gap-2">
          {(Object.keys(STATUS_LABEL) as ContentPlanStatus[]).map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                status === s
                  ? "bg-primary/20 text-primary border border-primary/30"
                  : "border border-border text-muted-foreground hover:text-foreground"
              }`}
            >
              {STATUS_LABEL[s]}
            </button>
          ))}
        </div>

        <div className="flex items-center justify-between gap-2">
          {plan ? (
            <button
              onClick={remove}
              disabled={busy}
              className="flex items-center gap-1.5 rounded-lg border border-red-500/30 px-3 py-2 text-sm font-medium text-red-400 transition-colors hover:bg-red-500/10 disabled:opacity-50"
            >
              <Trash2 className="h-4 w-4" />삭제
            </button>
          ) : (
            <span />
          )}
          <button
            onClick={save}
            disabled={busy}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "저장 중…" : "저장"}
          </button>
        </div>
      </div>
    </div>
  )
}
