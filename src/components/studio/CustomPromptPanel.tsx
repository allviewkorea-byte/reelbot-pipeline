"use client"

import { useState } from "react"
import { Sparkles } from "lucide-react"
import { BODY_ROLE, FACE_ROLE, USD_PER_IMAGE, roleName, usd, type GenItem, type RoleSlot, type StudioPresets } from "./studio-lib"

// 전문가 모드 — 직접 프롬프트. 저장할 역할 + 참조로 넣을 확정 사진(체크) + 장수. 프리셋·장면 규칙 없이 그대로
// 보내고 안전 필터 거부 시 자동 재시도만 적용(백엔드 plan(prompt, ref_roles)).

const ROLE_RE = /^[a-z0-9][a-z0-9_]{1,39}$/

export function CustomPromptPanel({ slots, presets, generating, onGenerate }: {
  slots: RoleSlot[]
  presets: StudioPresets
  generating: boolean
  onGenerate: (items: GenItem[]) => Promise<boolean>
}) {
  const confirmed = slots.filter((s) => s.confirmed)
  const [prompt, setPrompt] = useState("")
  const [refs, setRefs] = useState<string[]>(() => confirmed.filter((s) => s.role === FACE_ROLE || s.role === BODY_ROLE).map((s) => s.role))
  const [target, setTarget] = useState("custom_01")
  const [count, setCount] = useState(2)
  const targets = Array.from(new Set([target, FACE_ROLE, BODY_ROLE, ...presets.hair.map((h) => h.role), ...presets.pose.map((p) => p.role), ...slots.map((s) => s.role)]))
  const valid = ROLE_RE.test(target) && prompt.trim().length >= 10

  function toggle(role: string) {
    setRefs((prev) => (prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role].slice(0, 10)))
  }

  return (
    <div className="flex min-w-0 flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div>
        <h2 className="text-sm font-semibold text-foreground">직접 프롬프트</h2>
        <p className="text-xs text-muted-foreground">고른 사진을 참조로 넣고 그대로 만들어요. 안전 필터에 걸리면 표현을 바꿔 한 번 더 시도해요.</p>
      </div>
      <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={5} placeholder="영문 프롬프트"
        className="w-full min-w-0 resize-y rounded-lg border border-border bg-background p-2 text-xs leading-relaxed text-foreground" />
      <div className="flex min-w-0 flex-col gap-1.5">
        <p className="text-xs text-muted-foreground">참조 사진 ({refs.length}/10, 체크한 순서대로 1번부터)</p>
        {confirmed.length === 0 ? (
          <p className="text-xs text-muted-foreground">확정된 사진이 없어요 — 참조 없이 만들어요.</p>
        ) : (
          <div className="grid min-w-0 grid-cols-3 gap-2 sm:grid-cols-6">
            {confirmed.map((s) => {
              const on = refs.includes(s.role)
              return (
                <button key={s.role} type="button" onClick={() => toggle(s.role)} aria-pressed={on}
                  className={`relative flex min-w-0 flex-col gap-1 rounded-lg border p-1 text-left ${on ? "border-primary" : "border-border opacity-70"}`}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={s.confirmed!.url} alt="" className="aspect-[3/4] w-full rounded object-cover" />
                  <span className="truncate text-[11px] text-foreground">{roleName(s.role, presets)}</span>
                  {on && <span className="absolute right-1 top-1 rounded bg-primary px-1 text-[10px] font-medium text-primary-foreground">{refs.indexOf(s.role) + 1}</span>}
                </button>
              )
            })}
          </div>
        )}
      </div>
      <div className="flex min-w-0 flex-wrap items-end gap-2">
        <label className="flex min-w-0 flex-1 basis-40 flex-col gap-1 text-xs text-muted-foreground">
          저장할 역할
          <input list="studio-targets" value={target} onChange={(e) => setTarget(e.target.value.trim().toLowerCase())}
            className={`w-full min-w-0 rounded-lg border bg-background px-2 py-1.5 text-xs text-foreground ${ROLE_RE.test(target) ? "border-border" : "border-amber-500/50"}`} />
          <datalist id="studio-targets">{targets.map((t) => <option key={t} value={t}>{roleName(t, presets)}</option>)}</datalist>
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          장수
          <select value={count} onChange={(e) => setCount(Number(e.target.value))} className="rounded-lg border border-border bg-background px-2 py-1.5 text-xs text-foreground">
            {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}장</option>)}
          </select>
        </label>
        <button onClick={() => onGenerate([{ role: target, prompt: prompt.trim(), refs, count }])} disabled={!valid || generating}
          className="flex min-h-[36px] items-center gap-1.5 rounded-lg bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
          <Sparkles className="h-3.5 w-3.5" /> 만들기 · {usd(count * USD_PER_IMAGE)}
        </button>
      </div>
    </div>
  )
}
