"use client"

import { useEffect, useState } from "react"
import { toast } from "sonner"
import { CheckCircle2, Loader2, Ruler } from "lucide-react"
import { jsonOrThrow } from "./studio-lib"

// 치수 카드 — 키·어깨·가슴·허리·엉덩이·팔·다리안쪽(cm) + 평소 사이즈. 착장 핏을 이 숫자로 계산한다(꾸미지 않음).
// 저장 전 초안(채이 기본값)은 '초안'으로 보여 주고, 저장해야 착장을 만들 수 있다.

interface Field { key: string; label: string; unit: string; min?: number; max?: number }
interface Data { values: Record<string, string | number>; saved: boolean; draft: boolean; fields: Field[] }

export function MeasurementsCard({ characterId, onSaved }: { characterId: string; onSaved?: () => void }) {
  const [data, setData] = useState<Data | null>(null)
  const [values, setValues] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    fetch(`/api/studio/characters/${encodeURIComponent(characterId)}/measurements`, { cache: "no-store" })
      .then(jsonOrThrow)
      .then((d: Data) => {
        setData(d)
        setValues(Object.fromEntries(Object.entries(d.values ?? {}).map(([k, v]) => [k, String(v ?? "")])))
      })
      .catch(() => setData(null))
  }, [characterId])

  async function save() {
    setBusy(true)
    try {
      const d: Data = await jsonOrThrow(await fetch(`/api/studio/characters/${encodeURIComponent(characterId)}/measurements`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ values }),
      }))
      setData(d)
      toast.success("치수를 저장했어요")
      onSaved?.()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "저장하지 못했어요")
    } finally {
      setBusy(false)
    }
  }

  if (!data) return null
  const nums = data.fields.filter((f) => f.unit === "cm")
  const sizes = data.fields.filter((f) => f.unit !== "cm")

  return (
    <section className="flex min-w-0 flex-col gap-4 rounded-xl border border-border bg-card p-4">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <Ruler className="h-5 w-5 text-primary" />
        <h2 className="text-base font-semibold text-foreground">치수</h2>
        {data.saved ? (
          <span className="flex items-center gap-1 text-xs text-emerald-400"><CheckCircle2 className="h-3.5 w-3.5" /> 저장됨</span>
        ) : data.draft ? (
          <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs text-amber-400">초안 — 확인 후 저장해 주세요</span>
        ) : (
          <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs text-amber-400">입력이 필요해요</span>
        )}
      </div>
      <p className="text-xs text-muted-foreground">옷을 이 치수 그대로 입혀요. 실제보다 예쁘게 꾸미지 않아요.</p>
      <div className="grid min-w-0 grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
        {nums.map((f) => (
          <label key={f.key} className="flex min-w-0 flex-col gap-1 text-xs text-muted-foreground">
            {f.label}
            <div className="flex min-w-0 items-center gap-1">
              <input inputMode="decimal" value={values[f.key] ?? ""} onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                className="w-full min-w-0 rounded-lg border border-border bg-background px-2 py-2 text-sm text-foreground" />
              <span className="shrink-0">cm</span>
            </div>
          </label>
        ))}
      </div>
      <div className="grid min-w-0 grid-cols-3 gap-3">
        {sizes.map((f) => (
          <label key={f.key} className="flex min-w-0 flex-col gap-1 text-xs text-muted-foreground">
            {f.label}
            <input value={values[f.key] ?? ""} onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
              className="w-full min-w-0 rounded-lg border border-border bg-background px-2 py-2 text-sm text-foreground" />
          </label>
        ))}
      </div>
      <button onClick={save} disabled={busy}
        className="flex min-h-[44px] items-center justify-center gap-1.5 self-start rounded-lg bg-primary px-5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
        {busy && <Loader2 className="h-4 w-4 animate-spin" />} 치수 저장
      </button>
    </section>
  )
}
