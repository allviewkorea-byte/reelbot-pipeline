"use client"

import { useCallback, useEffect, useMemo, useState, type KeyboardEvent } from "react"
import { ChevronDown, ChevronUp, X, AlertTriangle, Loader2, RefreshCw } from "lucide-react"
import {
  BAEKGOM_CHANNEL_ID,
  CONTENT_CONCEPTS,
  CONTENT_SLOTS,
  CONCEPT_CONFLICT_WINDOW_DAYS,
  SLOT_BY_ID,
  DEFAULT_DAILY_CAP,
  clampDailyCap,
  slotsForCap,
  conceptColor,
  randomSlotTime,
  type ContentPlan,
  type ContentPlanStatus,
  type ContentSlot,
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

type DaySlots = Partial<Record<ContentSlot, ContentPlan>>

// 옛 데이터(slot 없음)는 morning 으로 간주(방어). 같은 슬롯 중복은 첫 행 우선.
function slotOf(p: ContentPlan): ContentSlot {
  return (p.slot ?? "morning") as ContentSlot
}

// 연속 컨셉 감지: 같은 컨셉이 앞뒤 N일 내 '다른 날'에도 있으면 충돌(plan id 집합).
// 슬롯 도입 후에도 행 단위로 그대로 동작(같은 날 내 중복은 아래 dupDates 로 별도 처리).
function detectConflicts(plans: ContentPlan[]): Set<string> {
  const conflict = new Set<string>()
  for (let i = 0; i < plans.length; i++) {
    for (let j = 0; j < plans.length; j++) {
      if (i === j) continue
      const a = plans[i]
      const b = plans[j]
      if (!a.concept || a.concept !== b.concept) continue
      if (a.date === b.date) continue // 같은 날은 dupDates 가 담당
      if (Math.abs(diffDays(a.date, b.date)) <= CONCEPT_CONFLICT_WINDOW_DAYS) {
        conflict.add(a.id)
      }
    }
  }
  return conflict
}

// 펼침(월간) 상태는 상위(page)가 소유 — 트렌드 패널과 짝으로 동시 펼침/접힘(controlled).
export function ContentCalendar({
  monthOpen,
  onToggleMonth,
}: {
  monthOpen: boolean
  onToggleMonth: () => void
}) {
  const [today] = useState(() => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return d
  })
  const [viewMonth, setViewMonth] = useState(() => ({ y: today.getFullYear(), m: today.getMonth() }))
  const [plans, setPlans] = useState<ContentPlan[]>([])
  const [loading, setLoading] = useState(true)
  const [editDate, setEditDate] = useState<string | null>(null)
  // 연속 컨셉 경고(⚠ + "연속 컨셉 N건") 표시 토글 — 자동 생성엔 거슬려 기본 꺼짐.
  // detectConflicts 계산은 그대로, 표시 여부만 제어. (하루 중복 경고는 항상 표시)
  const [showConflicts, setShowConflicts] = useState(false)
  // 하루 생산 개수(daily_cap) — 오늘의 콘텐츠를 cap 개수만큼만 표시(월간 그리드는 데이터 기준 자동).
  const [dailyCap, setDailyCap] = useState(DEFAULT_DAILY_CAP)

  // daily_cap 로드(대시보드 드롭다운과 같은 출처). 변경 즉시 반영을 위해 포커스 복귀 시 재조회.
  useEffect(() => {
    let alive = true
    const load = () =>
      fetch(`/api/channel-status?channelId=${BAEKGOM_CHANNEL_ID}`)
        .then((r) => r.json())
        .then((d) => {
          if (alive) setDailyCap(clampDailyCap(d?.dailyCap))
        })
        .catch(() => {})
    load()
    const onFocus = () => load()
    window.addEventListener("focus", onFocus)
    return () => {
      alive = false
      window.removeEventListener("focus", onFocus)
    }
  }, [])

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

  // 날짜 → 슬롯별 플랜 맵.
  const byDateSlot = useMemo(() => {
    const m = new Map<string, DaySlots>()
    for (const p of plans) {
      const slot = slotOf(p)
      if (!m.has(p.date)) m.set(p.date, {})
      const day = m.get(p.date)!
      if (!day[slot]) day[slot] = p
    }
    return m
  }, [plans])

  const conflicts = useMemo(() => detectConflicts(plans), [plans])
  const conflictDates = useMemo(
    () => new Set(plans.filter((p) => conflicts.has(p.id)).map((p) => p.date)),
    [plans, conflicts],
  )
  // 하루 같은 컨셉(슬롯 간 중복) — 경고 표시용.
  const dupDates = useMemo(() => {
    const byDate = new Map<string, string[]>()
    for (const p of plans) {
      if (!p.concept) continue
      const arr = byDate.get(p.date) ?? []
      arr.push(p.concept)
      byDate.set(p.date, arr)
    }
    const s = new Set<string>()
    for (const [date, concepts] of byDate) {
      if (new Set(concepts).size !== concepts.length) s.add(date)
    }
    return s
  }, [plans])

  const grid = useMemo(() => monthGrid(viewMonth.y, viewMonth.m), [viewMonth])

  // 셀 안의 슬롯별 컨셉 색 태그(아침→저녁→밤 순). compact: 9px/10px.
  const slotTags = (iso: string, size: "wk" | "mo") => {
    const day = byDateSlot.get(iso)
    if (!day) return null
    const rows = CONTENT_SLOTS.map((s) => day[s.id]).filter(Boolean) as ContentPlan[]
    if (rows.length === 0) return null
    return (
      <span className="flex flex-col gap-0.5">
        {rows.map((p) => (
          <span
            key={p.id}
            className={`flex items-center gap-1 truncate leading-tight ${size === "wk" ? "text-[10px]" : "text-[9px]"}`}
          >
            <span
              className="h-1.5 w-1.5 shrink-0 rounded-full"
              style={{ backgroundColor: conceptColor(p.concept) }}
            />
            <span className="truncate" style={{ color: conceptColor(p.concept) }}>
              {p.concept}
            </span>
          </span>
        ))}
      </span>
    )
  }

  return (
    <div className="rounded-xl border border-border bg-card p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          {monthOpen ? "월간 계획서" : "오늘의 콘텐츠"}
          {loading && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
          {showConflicts && conflictDates.size > 0 && (
            <span className="flex items-center gap-1 text-xs font-normal text-amber-400">
              <AlertTriangle className="h-3.5 w-3.5" />연속 컨셉 {conflictDates.size}건
            </span>
          )}
          {dupDates.size > 0 && (
            <span className="flex items-center gap-1 text-xs font-normal text-red-400">
              <AlertTriangle className="h-3.5 w-3.5" />하루 중복 {dupDates.size}건
            </span>
          )}
        </h2>
        <div className="flex items-center gap-2">
          {/* 연속 경고 ON/OFF 스위치 — 월간 계획서에서만, '접기' 버튼 바로 왼쪽. 기본 꺼짐. */}
          {monthOpen && (
            <button
              onClick={() => setShowConflicts((v) => !v)}
              role="switch"
              aria-checked={showConflicts}
              className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              연속 경고
              <span
                className={`relative h-4 w-7 shrink-0 rounded-full transition-colors ${
                  showConflicts ? "bg-primary" : "bg-secondary"
                }`}
              >
                <span
                  className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${
                    showConflicts ? "left-3.5" : "left-0.5"
                  }`}
                />
              </span>
            </button>
          )}
          <button
            onClick={onToggleMonth}
            aria-expanded={monthOpen}
            className="flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-primary/5"
          >
            {monthOpen ? "접기" : "전체 보기"}
            {monthOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* 오늘의 콘텐츠 — 오늘 날짜 cap 개수만큼 슬롯 표시(cap=1 저녁/2 저녁+밤/3 현행).
          status 로 완료/미완료 색 구분. */}
      {!monthOpen && (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {slotsForCap(dailyCap).map((s) => {
            const p = (byDateSlot.get(toISO(today)) ?? {})[s.id]
            const st = p?.status
            const cardCls = !p
              ? "border-dashed border-border/50 hover:bg-secondary/20"
              : st === "done"
                ? "border-emerald-500/40 bg-emerald-500/10"
                : st === "skipped"
                  ? "border-border/40 opacity-50"
                  : "border-border/60 hover:bg-secondary/30"
            const statusCls =
              st === "done"
                ? "text-emerald-400"
                : st === "skipped"
                  ? "text-muted-foreground/60"
                  : "text-muted-foreground"
            return (
              <button
                key={s.id}
                onClick={() => setEditDate(toISO(today))}
                className={`flex min-h-[52px] flex-col gap-1 rounded-lg border p-2.5 text-left transition-colors ${cardCls}`}
              >
                <div className="flex items-center justify-between gap-1">
                  <span className="text-xs font-medium text-foreground">
                    {s.label}
                    <span className="ml-1 text-[10px] font-normal text-muted-foreground">
                      {s.startHour}~{s.endHour}시
                    </span>
                  </span>
                  {p && <span className={`text-[10px] font-medium ${statusCls}`}>{STATUS_LABEL[st!]}</span>}
                </div>
                {p ? (
                  <span className="flex items-center gap-1.5 truncate text-xs">
                    <span
                      className="h-1.5 w-1.5 shrink-0 rounded-full"
                      style={{ backgroundColor: conceptColor(p.concept) }}
                    />
                    <span className="truncate font-medium" style={{ color: conceptColor(p.concept) }}>
                      {p.concept}
                    </span>
                    {p.scheduled_time && (
                      <span className="ml-auto shrink-0 font-mono text-[10px] text-muted-foreground">
                        {p.scheduled_time}
                      </span>
                    )}
                  </span>
                ) : (
                  <span className="text-xs text-muted-foreground/50">미정</span>
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
              const inMonth = d.getMonth() === viewMonth.m
              const isToday = iso === toISO(today)
              const warn = dupDates.has(iso) || (showConflicts && conflictDates.has(iso))
              return (
                <button
                  key={iso}
                  onClick={() => setEditDate(iso)}
                  className={`flex min-h-[56px] flex-col gap-0.5 rounded-md border p-1.5 text-left transition-colors ${
                    isToday ? "border-primary/50" : "border-border/40"
                  } ${inMonth ? "hover:bg-secondary/30" : "opacity-40"}`}
                >
                  <span className="flex items-center gap-0.5 text-[11px] text-muted-foreground">
                    {warn && <AlertTriangle className="h-2.5 w-2.5 shrink-0 text-amber-400" />}
                    {d.getDate()}
                  </span>
                  {slotTags(iso, "mo")}
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
        <DayEditor
          date={editDate}
          daySlots={byDateSlot.get(editDate) ?? {}}
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

// 슬롯 1개의 편집 초안.
interface SlotDraft {
  enabled: boolean
  id?: string
  concept: string
  title: string
  memo: string
  status: ContentPlanStatus
  time: string // HH:MM
}

function DayEditor({
  date,
  daySlots,
  onClose,
  onSaved,
}: {
  date: string
  daySlots: DaySlots
  onClose: () => void
  onSaved: () => void
}) {
  const [drafts, setDrafts] = useState<Record<ContentSlot, SlotDraft>>(() => {
    const init = {} as Record<ContentSlot, SlotDraft>
    for (const s of CONTENT_SLOTS) {
      const p = daySlots[s.id]
      init[s.id] = {
        enabled: Boolean(p),
        id: p?.id,
        concept: p?.concept || CONTENT_CONCEPTS[0],
        title: p?.title || "",
        memo: p?.memo || "",
        status: p?.status || "planned",
        time: p?.scheduled_time || randomSlotTime(s.id),
      }
    }
    return init
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const patch = (slot: ContentSlot, p: Partial<SlotDraft>) =>
    setDrafts((prev) => ({ ...prev, [slot]: { ...prev[slot], ...p } }))

  // 하루 같은 컨셉 금지: 켜진 슬롯들의 컨셉이 겹치면 저장 차단.
  const enabledConcepts = CONTENT_SLOTS.filter((s) => drafts[s.id].enabled).map((s) => drafts[s.id].concept)
  const dupConcept = enabledConcepts.length !== new Set(enabledConcepts).size

  const save = async () => {
    if (busy || dupConcept) return
    setBusy(true)
    setError(null)
    try {
      let ok = true
      for (const s of CONTENT_SLOTS) {
        const d = drafts[s.id]
        if (d.enabled) {
          const res = await fetch("/api/content-plans", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              id: d.id,
              date,
              slot: s.id,
              scheduled_time: d.time,
              concept: d.concept,
              title: d.title.trim() || null,
              memo: d.memo.trim() || null,
              status: d.status,
            }),
          })
          if (!res.ok) ok = false
        } else if (d.id) {
          // 이전엔 켜져 있던 슬롯 → 끄면 행 삭제.
          const res = await fetch(`/api/content-plans/${encodeURIComponent(d.id)}`, { method: "DELETE" })
          if (!res.ok) ok = false
        }
      }
      if (ok) onSaved()
      else setError("저장 실패 — slot/scheduled_time 컬럼(ALTER) 적용 여부를 확인하세요.")
    } catch {
      setError("저장 중 오류가 발생했습니다.")
    } finally {
      setBusy(false)
    }
  }

  // Enter=저장(컨셉 중복 없을 때). IME 한글 조합 중 Enter 무시.
  const onTitleKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== "Enter" || e.nativeEvent.isComposing) return
    e.preventDefault()
    if (!busy && !dupConcept) save()
  }
  // 메모: Enter=저장 / Ctrl(⌘)+Enter=줄바꿈 삽입.
  const onMemoKey = (e: KeyboardEvent<HTMLTextAreaElement>, slot: ContentSlot) => {
    if (e.key !== "Enter" || e.nativeEvent.isComposing) return
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault()
      const ta = e.currentTarget
      const start = ta.selectionStart
      const end = ta.selectionEnd
      const memo = drafts[slot].memo
      patch(slot, { memo: memo.slice(0, start) + "\n" + memo.slice(end) })
      requestAnimationFrame(() => {
        ta.selectionStart = ta.selectionEnd = start + 1
      })
      return
    }
    e.preventDefault()
    if (!busy && !dupConcept) save()
  }

  // CloneModal 오버레이 패턴 재사용(Sheet/Dialog 없음).
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="max-h-[85vh] w-full max-w-4xl overflow-y-auto rounded-xl border border-border bg-card p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-base font-semibold text-foreground">{date} · 하루 3슬롯</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground" aria-label="닫기">
            <X className="h-4 w-4" />
          </button>
        </div>

        {dupConcept && (
          <div className="mb-3 flex items-center gap-1.5 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs font-medium text-red-400">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            하루 같은 컨셉은 안 됩니다 — 슬롯마다 다른 컨셉으로 바꿔주세요.
          </div>
        )}
        {error && (
          <div className="mb-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs font-medium text-red-400">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {CONTENT_SLOTS.map((s) => {
            const d = drafts[s.id]
            const def = SLOT_BY_ID[s.id]
            return (
              <div
                key={s.id}
                className={`flex flex-col gap-2 rounded-lg border p-3 transition-colors ${
                  d.enabled ? "border-border bg-background/40" : "border-border/40"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-semibold text-foreground">
                    {def.label}
                    <span className="ml-1 text-[11px] font-normal text-muted-foreground">
                      {def.startHour}~{def.endHour}시
                    </span>
                  </span>
                  <button
                    onClick={() => patch(s.id, { enabled: !d.enabled })}
                    aria-pressed={d.enabled}
                    className={`rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors ${
                      d.enabled
                        ? "bg-emerald-500/15 text-emerald-400"
                        : "border border-border text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {d.enabled ? "사용" : "꺼짐"}
                  </button>
                </div>

                {d.enabled && (
                  <>
                    {/* 시각 — 구간 내 랜덤 자동. 재생성 가능. */}
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-semibold text-foreground">{d.time}</span>
                      <button
                        onClick={() => patch(s.id, { time: randomSlotTime(s.id) })}
                        className="flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
                      >
                        <RefreshCw className="h-3 w-3" />재생성
                      </button>
                    </div>

                    {/* 컨셉 — 색으로 구분 */}
                    <div className="flex flex-wrap gap-1.5">
                      {CONTENT_CONCEPTS.map((c) => {
                        const selected = d.concept === c
                        return (
                          <button
                            key={c}
                            onClick={() => patch(s.id, { concept: c })}
                            style={selected ? { color: conceptColor(c), borderColor: conceptColor(c) } : undefined}
                            className={`rounded-full border px-2 py-0.5 text-[11px] font-medium transition-colors ${
                              selected ? "bg-white/5" : "border-border text-muted-foreground hover:text-foreground"
                            }`}
                          >
                            {c}
                          </button>
                        )
                      })}
                    </div>

                    <input
                      className={FIELD}
                      value={d.title}
                      onChange={(e) => patch(s.id, { title: e.target.value })}
                      onKeyDown={onTitleKey}
                      placeholder="제목 (선택)"
                    />

                    <div className="flex gap-1.5">
                      {(Object.keys(STATUS_LABEL) as ContentPlanStatus[]).map((st) => (
                        <button
                          key={st}
                          onClick={() => patch(s.id, { status: st })}
                          className={`rounded-md px-2 py-1 text-[11px] font-medium transition-colors ${
                            d.status === st
                              ? "bg-primary/20 text-primary border border-primary/30"
                              : "border border-border text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          {STATUS_LABEL[st]}
                        </button>
                      ))}
                    </div>

                    <textarea
                      className={`${FIELD} min-h-12 resize-y`}
                      value={d.memo}
                      onChange={(e) => patch(s.id, { memo: e.target.value })}
                      onKeyDown={(e) => onMemoKey(e, s.id)}
                      placeholder="메모 (선택)"
                    />
                  </>
                )}
              </div>
            )
          })}
        </div>

        <div className="mt-4 flex items-center justify-between gap-2">
          <p className="text-[11px] text-muted-foreground">Enter 저장 · Ctrl(⌘)+Enter 줄바꿈 · 시각은 구간 내 랜덤</p>
          <button
            onClick={save}
            disabled={busy || dupConcept}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "저장 중…" : "저장"}
          </button>
        </div>
      </div>
    </div>
  )
}
