"use client"

import { useCallback, useMemo, useState } from "react"
import { Shuffle } from "lucide-react"
import { cn } from "@/lib/utils"
import {
  ACTION_TAGS,
  CHIP_AXES,
  getHiddenChips,
  type TagCombo,
  type TagAxis,
} from "@/lib/music-tags"

interface Props {
  disabled?: boolean
  onChange: (combo: TagCombo | null) => void
}

export function TagComboSelector({ disabled, onChange }: Props) {
  const [action, setAction] = useState<string | null>(null)
  const [chips, setChips] = useState<Record<string, string[]>>({})
  const [revealedStep, setRevealedStep] = useState(0)

  const hidden = useMemo(() => getHiddenChips(action), [action])

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

  const handleAction = useCallback(
    (id: string) => {
      const next = id === "" ? null : id
      setAction(next)
      if (next && revealedStep === 0) setRevealedStep(1)
      const cleaned = { ...chips }
      if (next) {
        const h = getHiddenChips(next)
        for (const [axis, hiddenIds] of Object.entries(h)) {
          if (cleaned[axis]) {
            cleaned[axis] = cleaned[axis].filter((t) => !hiddenIds.has(t))
          }
        }
      }
      setChips(cleaned)
      onChange(buildCombo(next, cleaned))
    },
    [chips, revealedStep, onChange, buildCombo],
  )

  const toggleChip = useCallback(
    (axis: string, id: string) => {
      const prev = chips[axis] || []
      const next = prev.includes(id)
        ? prev.filter((t) => t !== id)
        : [...prev, id]
      const updated = { ...chips, [axis]: next }
      setChips(updated)
      onChange(buildCombo(action, updated))
    },
    [chips, action, onChange, buildCombo],
  )

  const advanceStep = useCallback(() => {
    if (revealedStep < CHIP_AXES.length) setRevealedStep((s) => s + 1)
  }, [revealedStep])

  const handleRandom = useCallback(() => {
    const presets = [
      { action: "study", genre: ["lofi"], emotion: ["calm"], tempo: ["gentle"] },
      { action: "drive", genre: ["citypop"], emotion: ["happy"], tempo: ["moderate"] },
      { action: "rest", genre: ["jazz", "acoustic"], emotion: ["peaceful"], tempo: ["relaxed"] },
      { action: "workout", genre: ["electronic"], emotion: ["passionate"], tempo: ["fast"] },
      { action: "sleep", genre: ["ambient", "piano"], emotion: ["drowsy"], tempo: ["gentle"] },
      { action: "cafe", genre: ["bossanova", "acoustic"], emotion: ["warm"], tempo: ["relaxed"] },
      { action: "date", genre: ["rnb", "neosoul"], emotion: ["excited"], tempo: ["moderate"] },
      { action: "walk", genre: ["indie", "dreampop"], emotion: ["free"], tempo: ["lively"] },
      { action: "coding", genre: ["lofihiphop"], emotion: ["calm"], tempo: ["moderate"] },
      { action: "meditation", genre: ["ambient", "newage"], emotion: ["peaceful"], tempo: ["gentle"], format: ["instrumental"] },
    ]
    const pick = presets[Math.floor(Math.random() * presets.length)]
    setAction(pick.action)
    const newChips: Record<string, string[]> = {}
    const pickAny = pick as Record<string, unknown>
    for (const key of ["genre", "situation", "emotion", "tempo", "format", "charm"]) {
      const val = pickAny[key]
      if (Array.isArray(val)) newChips[key] = val as string[]
    }
    setChips(newChips)
    setRevealedStep(CHIP_AXES.length)
    onChange(buildCombo(pick.action, newChips))
  }, [onChange, buildCombo])

  const handleClear = useCallback(() => {
    setAction(null)
    setChips({})
    setRevealedStep(0)
    onChange(null)
  }, [onChange])

  const visibleAxes = useMemo(
    () => CHIP_AXES.slice(0, revealedStep),
    [revealedStep],
  )

  const selectedCount = useMemo(() => {
    let c = action ? 1 : 0
    for (const v of Object.values(chips)) c += v.length
    return c
  }, [action, chips])

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-medium text-muted-foreground">
          태그 조합 {selectedCount > 0 && <span className="text-primary">({selectedCount})</span>}
        </span>
        <div className="flex gap-1">
          <button
            type="button"
            onClick={handleRandom}
            disabled={disabled}
            className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] text-muted-foreground hover:text-primary disabled:opacity-50"
            title="랜덤 조합"
          >
            <Shuffle className="h-3 w-3" /> 랜덤
          </button>
          {selectedCount > 0 && (
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

      {/* 축2~7: 칩 기반 (순차 공개) */}
      {visibleAxes.map((axis: TagAxis) => (
        <ChipGroup
          key={axis.key}
          axis={axis}
          selected={chips[axis.key] || []}
          hidden={hidden[axis.key]}
          disabled={disabled}
          onToggle={(id) => toggleChip(axis.key, id)}
        />
      ))}

      {/* 다음 축 공개 버튼 */}
      {revealedStep > 0 && revealedStep < CHIP_AXES.length && (
        <button
          type="button"
          onClick={advanceStep}
          disabled={disabled}
          className="self-start rounded-md border border-dashed border-border px-2 py-1 text-[10px] text-muted-foreground hover:border-primary/40 hover:text-foreground disabled:opacity-50"
        >
          + {CHIP_AXES[revealedStep].emoji} {CHIP_AXES[revealedStep].label_kr}
        </button>
      )}
    </div>
  )
}

function ChipGroup({
  axis,
  selected,
  hidden,
  disabled,
  onToggle,
}: {
  axis: TagAxis
  selected: string[]
  hidden?: Set<string>
  disabled?: boolean
  onToggle: (id: string) => void
}) {
  const visible = useMemo(
    () => axis.tags.filter((t) => !hidden?.has(t.id)),
    [axis.tags, hidden],
  )

  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] text-muted-foreground">
        {axis.emoji} {axis.label_kr}
      </span>
      <div className="flex flex-wrap gap-1">
        {visible.map((t) => {
          const on = selected.includes(t.id)
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => onToggle(t.id)}
              disabled={disabled}
              className={cn(
                "rounded-full border px-2 py-0.5 text-[10px] transition-colors",
                on
                  ? "border-primary/60 bg-primary/20 text-primary"
                  : "border-border text-muted-foreground hover:border-primary/30 hover:text-foreground",
                disabled && "opacity-50",
              )}
            >
              {t.label_kr}
            </button>
          )
        })}
      </div>
    </div>
  )
}
