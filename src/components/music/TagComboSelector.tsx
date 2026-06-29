"use client"

import { useCallback, useMemo, useState } from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"
import {
  ACTION_TAGS,
  CHIP_AXES,
  getHiddenChips,
  type TagCombo,
} from "@/lib/music-tags"

interface Props {
  disabled?: boolean
  onChange: (combo: TagCombo | null) => void
}

export function TagComboSelector({ disabled, onChange }: Props) {
  const [action, setAction] = useState<string | null>(null)
  const [chips, setChips] = useState<Record<string, string[]>>({})
  const [currentStep, setCurrentStep] = useState(0)

  const buildCombo = useCallback(
    (a: string | null, c: Record<string, string[]>): TagCombo | null => {
      const hasAny = a || Object.values(c).some((v) => v.length > 0)
      if (!hasAny) return null
      const combo: TagCombo = {}
      if (a) combo.action = a
      for (const axis of CHIP_AXES) {
        const sel = c[axis.key]
        if (sel?.length) (combo as Record<string, unknown>)[axis.key] = sel
      }
      return combo
    },
    [],
  )

  const hidden = useMemo(() => {
    const combo = buildCombo(action, chips)
    return getHiddenChips(action, combo)
  }, [action, chips, buildCombo])

  const handleAction = useCallback(
    (id: string) => {
      const next = id === "" ? null : id
      setAction(next)
      setCurrentStep(0)
      const cleaned = { ...chips }
      if (next) {
        const h = getHiddenChips(next, buildCombo(next, cleaned))
        for (const [axis, hiddenIds] of Object.entries(h)) {
          if (cleaned[axis]) {
            cleaned[axis] = cleaned[axis].filter((t) => !hiddenIds.has(t))
          }
        }
      }
      setChips(cleaned)
      onChange(buildCombo(next, cleaned))
    },
    [chips, onChange, buildCombo],
  )

  const toggleChip = useCallback(
    (axis: string, id: string) => {
      const prev = chips[axis] || []
      let next = prev.includes(id)
        ? prev.filter((t) => t !== id)
        : [...prev, id]
      if (axis === "format" && next.includes(id)) {
        const combo = buildCombo(action, { ...chips, [axis]: next })
        const h = getHiddenChips(action, combo)
        if (h.format) {
          next = next.filter((t) => !h.format!.has(t))
        }
      }
      const updated = { ...chips, [axis]: next }
      setChips(updated)
      onChange(buildCombo(action, updated))
    },
    [chips, action, onChange, buildCombo],
  )

  const handleClear = useCallback(() => {
    setAction(null)
    setChips({})
    setCurrentStep(0)
    onChange(null)
  }, [onChange])

  const chipCount = useMemo(() => {
    let c = 0
    for (const v of Object.values(chips)) c += v.length
    return c
  }, [chips])

  const currentAxis = CHIP_AXES[currentStep]
  const visibleTags = useMemo(
    () => currentAxis.tags.filter((t) => !hidden[currentAxis.key]?.has(t.id)),
    [currentAxis, hidden],
  )
  const currentSelected = chips[currentAxis.key] || []

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-medium text-muted-foreground">태그 조합</span>
        {(action || chipCount > 0) && (
          <button
            type="button"
            onClick={handleClear}
            disabled={disabled}
            className="rounded px-1.5 py-0.5 text-[10px] text-muted-foreground hover:text-red-400 disabled:opacity-50"
          >
            초기화
          </button>
        )}
      </div>

      {/* 축1: 어떨때 드롭다운 */}
      <select
        value={action || ""}
        onChange={(e) => handleAction(e.target.value)}
        disabled={disabled}
        className="h-7 rounded-md border border-border bg-background px-1.5 text-xs text-foreground"
      >
        <option value="">어떨때?</option>
        {ACTION_TAGS.map((t) => (
          <option key={t.id} value={t.id}>{t.label_kr}</option>
        ))}
      </select>

      {/* 축2~7: 단계 카드 — 어떨때 선택 후에만 표시 */}
      {action && (
        <>
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-muted-foreground">
              {currentAxis.emoji} {currentAxis.label_kr}
              <span className="ml-1 text-muted-foreground/60">({currentStep + 1}/{CHIP_AXES.length})</span>
              {currentSelected.length > 0 && (
                <span className="ml-1 text-primary">{currentSelected.length}개</span>
              )}
            </span>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {visibleTags.map((t) => {
              const on = currentSelected.includes(t.id)
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => toggleChip(currentAxis.key, t.id)}
                  disabled={disabled}
                  className={cn(
                    "rounded-md border px-2 py-1 text-xs transition-colors",
                    on
                      ? "border-primary/40 bg-primary/15 text-primary"
                      : "border-border text-muted-foreground hover:border-primary/30 hover:text-foreground",
                    disabled && "opacity-50",
                  )}
                >
                  {t.label_kr}
                </button>
              )
            })}
          </div>

          {/* 이전/다음 버튼 */}
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => setCurrentStep((s) => s - 1)}
              disabled={disabled || currentStep === 0}
              className={cn(
                "inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[11px] transition-colors",
                currentStep === 0
                  ? "text-muted-foreground/40"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <ChevronLeft className="h-3 w-3" /> 이전
            </button>
            <button
              type="button"
              onClick={() => setCurrentStep((s) => s + 1)}
              disabled={disabled || currentStep === CHIP_AXES.length - 1}
              className={cn(
                "inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[11px] transition-colors",
                currentStep === CHIP_AXES.length - 1
                  ? "text-muted-foreground/40"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              다음 <ChevronRight className="h-3 w-3" />
            </button>
          </div>
        </>
      )}
    </div>
  )
}
