"use client"

import { useMemo, useState } from "react"
import { toast } from "sonner"
import { CheckCircle2, Loader2, Pencil, Plus, Sparkles, X } from "lucide-react"
import { BODY_ROLE, FACE_ROLE, USD_PER_IMAGE, jsonOrThrow, usd, type GenItem, type PresetItem, type RoleSlot, type StudioPresets } from "./studio-lib"

// AI로 만들기 — ① 얼굴 후보 4장 → ② 체형 시트 2장 → ③ 헤어(체크한 것만 각 2장) → ④ 포즈(선택).
// 앞 단계가 확정돼야 다음 단계 버튼이 열린다. 버튼 옆에 예상 장수 × $0.011. 프리셋은 추가·삭제 가능.

const FACE_COUNT = 4
const COUNT = 2

function Step({ n, title, done, children }: { n: number; title: string; done: boolean; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-lg border border-border bg-background p-2.5">
      <div className="flex items-center gap-2">
        <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${done ? "bg-emerald-500/15 text-emerald-400" : "bg-primary/20 text-primary"}`}>
          {done ? <CheckCircle2 className="h-3.5 w-3.5" /> : n}
        </span>
        <p className="text-sm font-medium text-foreground">{title}</p>
      </div>
      {children}
    </div>
  )
}

function GenButton({ count, disabled, onClick, children }: { count: number; disabled: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled || count === 0}
      className="flex min-h-[34px] items-center gap-1.5 self-start rounded-lg bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
    >
      <Sparkles className="h-3.5 w-3.5" />
      {children}
      <span className="opacity-80">· {count}장 · {usd(count * USD_PER_IMAGE)}</span>
    </button>
  )
}

function PresetChecklist({ kind, characterId, items, slots, disabled, generating, onGenerate, onSaved }: {
  kind: "hair" | "pose"
  characterId: string
  items: PresetItem[]
  slots: Record<string, RoleSlot>
  disabled: boolean
  generating: boolean
  onGenerate: (items: GenItem[]) => Promise<boolean>
  onSaved: () => Promise<unknown>
}) {
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [editing, setEditing] = useState(false)
  const [newKey, setNewKey] = useState("")
  const [newLine, setNewLine] = useState("")
  const [saving, setSaving] = useState(false)
  const picked = items.filter((p) => checked.has(p.role))

  function toggle(role: string) {
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(role)) next.delete(role)
      else next.add(role)
      return next
    })
  }

  async function save(list: { key: string; line: string; label?: string }[]) {
    setSaving(true)
    try {
      await jsonOrThrow(await fetch(`/api/studio/characters/${encodeURIComponent(characterId)}/presets`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kind, items: list }),
      }))
      await onSaved()
      return true
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "프리셋 저장 실패")
      return false
    } finally {
      setSaving(false)
    }
  }

  const plain = (list: PresetItem[]) => list.map(({ key, line, label }) => (label ? { key, line, label } : { key, line }))

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <button onClick={() => setChecked(new Set(items.filter((p) => !slots[p.role]?.confirmed).map((p) => p.role)))} disabled={disabled} className="text-muted-foreground hover:text-foreground disabled:opacity-50">미확정 전부</button>
        <button onClick={() => setChecked(new Set())} disabled={disabled} className="text-muted-foreground hover:text-foreground disabled:opacity-50">선택 해제</button>
        <button onClick={() => setEditing((v) => !v)} className="ml-auto flex items-center gap-1 text-muted-foreground hover:text-foreground">
          <Pencil className="h-3 w-3" /> {editing ? "편집 끝" : "프리셋 편집"}
        </button>
      </div>
      <div className="grid min-w-0 gap-1 sm:grid-cols-2">
        {items.map((p) => {
          const done = !!slots[p.role]?.confirmed
          return (
            <label key={p.role} className={`flex min-w-0 items-start gap-1.5 rounded-md border border-border px-2 py-1.5 text-xs ${disabled ? "opacity-60" : "hover:border-primary/40"}`}>
              <input type="checkbox" className="mt-0.5 shrink-0" checked={checked.has(p.role)} disabled={disabled} onChange={() => toggle(p.role)} />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1 font-medium text-foreground">
                  <span className="truncate">{p.label || p.role}</span>
                  {done && <CheckCircle2 className="h-3 w-3 shrink-0 text-emerald-400" />}
                </span>
                <span className="block break-words text-[11px] text-muted-foreground">{p.line}</span>
              </span>
              {editing && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault()
                    if (window.confirm(`${p.role} 프리셋을 삭제할까요? (이미 만든 이미지는 그대로예요)`)) save(plain(items.filter((x) => x.role !== p.role)))
                  }}
                  disabled={saving}
                  aria-label="프리셋 삭제"
                  className="shrink-0 text-muted-foreground hover:text-red-400"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </label>
          )
        })}
      </div>
      {editing && (
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          <input value={newKey} onChange={(e) => setNewKey(e.target.value.trim().toLowerCase())} placeholder="키(영문, 예: bob)" className="w-32 min-w-0 rounded-md border border-border bg-background px-1.5 py-1 text-xs text-foreground" />
          <input value={newLine} onChange={(e) => setNewLine(e.target.value)} placeholder="영문 한 줄 (예: short chin-length bob)" className="min-w-0 flex-1 basis-48 rounded-md border border-border bg-background px-1.5 py-1 text-xs text-foreground" />
          <button
            onClick={async () => {
              if (await save([...plain(items), { key: newKey, line: newLine.trim() }])) {
                setNewKey("")
                setNewLine("")
              }
            }}
            disabled={saving || !newKey || newLine.trim().length < 5}
            className="flex min-h-[30px] items-center gap-1 rounded-lg border border-border px-2 text-xs text-foreground hover:border-primary/40 disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />} 추가
          </button>
        </div>
      )}
      <GenButton
        count={picked.length * COUNT}
        disabled={disabled || generating}
        onClick={async () => {
          if (await onGenerate(picked.map((p) => ({ role: p.role, count: COUNT })))) setChecked(new Set())
        }}
      >
        선택한 {picked.length}종 × {COUNT}장 만들기
      </GenButton>
    </div>
  )
}

export function GeneratePanel({ characterId, slots, presets, generating, onGenerate, onSaved }: {
  characterId: string
  slots: RoleSlot[]
  presets: StudioPresets
  generating: boolean
  onGenerate: (items: GenItem[]) => Promise<boolean>
  onSaved: () => Promise<unknown>
}) {
  const bySlot = useMemo(() => Object.fromEntries(slots.map((s) => [s.role, s])), [slots])
  const hasFace = !!bySlot[FACE_ROLE]?.confirmed
  const hasBody = !!bySlot[BODY_ROLE]?.confirmed

  return (
    <div className="flex min-w-0 flex-col gap-3 rounded-xl border border-border bg-card p-3">
      <div>
        <h2 className="text-sm font-semibold text-foreground">AI로 만들기</h2>
        <p className="text-[11px] text-muted-foreground">버튼만 누르면 돼요. 후보가 아래 역할 카드에 생기면 마음에 드는 것을 눌러 확정하세요.</p>
      </div>
      <div className="grid min-w-0 gap-2 lg:grid-cols-2">
        <Step n={1} title="얼굴" done={hasFace}>
          <p className="text-[11px] text-muted-foreground">캐릭터 설명으로 얼굴 후보를 만들어요. 1장을 골라 확정하면 다음 단계가 열려요.</p>
          <GenButton count={FACE_COUNT} disabled={generating} onClick={() => onGenerate([{ role: FACE_ROLE, count: FACE_COUNT }])}>
            얼굴 후보 만들기
          </GenButton>
        </Step>
        <Step n={2} title="체형 시트" done={hasBody}>
          <p className="text-[11px] text-muted-foreground">확정 얼굴 그대로 밝은 회색 운동복 정면+측면 시트를 만들어요.</p>
          <GenButton count={COUNT} disabled={generating || !hasFace} onClick={() => onGenerate([{ role: BODY_ROLE, count: COUNT }])}>
            체형 후보 만들기
          </GenButton>
          {!hasFace && <p className="text-[11px] text-amber-400">얼굴을 먼저 확정해 주세요.</p>}
        </Step>
        <Step n={3} title="헤어 라이브러리" done={presets.hair.length > 0 && presets.hair.every((h) => bySlot[h.role]?.confirmed)}>
          {!hasFace && <p className="text-[11px] text-amber-400">얼굴을 먼저 확정해 주세요.</p>}
          <PresetChecklist kind="hair" characterId={characterId} items={presets.hair} slots={bySlot} disabled={!hasFace} generating={generating} onGenerate={onGenerate} onSaved={onSaved} />
        </Step>
        <Step n={4} title="포즈 샘플 (선택)" done={presets.pose.length > 0 && presets.pose.every((p) => bySlot[p.role]?.confirmed)}>
          <p className="text-[11px] text-muted-foreground">얼굴은 가리고(어깨 아래 / 폰으로 가린 미러셀카), 신발이 보이면 현관·엘리베이터·야외에서만 찍어요.</p>
          {!(hasFace && hasBody) && <p className="text-[11px] text-amber-400">얼굴·체형을 먼저 확정해 주세요.</p>}
          <PresetChecklist kind="pose" characterId={characterId} items={presets.pose} slots={bySlot} disabled={!(hasFace && hasBody)} generating={generating} onGenerate={onGenerate} onSaved={onSaved} />
        </Step>
      </div>
    </div>
  )
}
