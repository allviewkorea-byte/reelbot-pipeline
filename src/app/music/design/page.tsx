"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { ArrowLeft, Loader2, Save } from "lucide-react"
import {
  DEFAULT_DESIGN_CONFIG,
  DESIGN_PRESET_FONTS,
  type MusicDesignConfig,
  type TextStyleConfig,
} from "@/lib/music"

// 미리보기용 Google Fonts(프리셋 10종) — Remotion 렌더와 동일 패밀리. 가중치는 기본 로드(미리보기는 faux-bold 허용).
const FONT_LINK =
  "https://fonts.googleapis.com/css2?" +
  DESIGN_PRESET_FONTS.map((f) => "family=" + f.replace(/ /g, "+")).join("&") +
  "&display=swap"

const WEIGHTS = [100, 200, 300, 400, 500, 600, 700, 800, 900]

export default function MusicDesignPage() {
  const [config, setConfig] = useState<MusicDesignConfig>(DEFAULT_DESIGN_CONFIG)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetch("/api/music/design-config")
      .then((r) => r.json())
      .then((d) => { if (d?.design_config) setConfig(d.design_config) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const patchTarget = (target: keyof MusicDesignConfig, patch: Partial<TextStyleConfig>) =>
    setConfig((c) => ({ ...c, [target]: { ...c[target], ...patch } }))

  const save = useCallback(async () => {
    setSaving(true)
    try {
      const res = await fetch("/api/music/design-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ play_list: config.play_list, where_label: config.where_label }),
      })
      const d = await res.json()
      if (!d?.ok) throw new Error(d?.detail || "저장 실패")
      if (d.design_config) setConfig(d.design_config)
      toast.success("디자인 설정을 저장했습니다.")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "저장 실패")
    } finally {
      setSaving(false)
    }
  }, [config])

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-auto p-4 md:p-6">
      <link rel="stylesheet" href={FONT_LINK} />
      <header className="flex items-center gap-3 pl-10 md:pl-0">
        <Link href="/music" className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground hover:bg-white/5 hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> 대시보드
        </Link>
        <div>
          <h1 className="text-xl font-semibold text-foreground">디자인 본부</h1>
          <p className="text-sm text-muted-foreground">PLAY LIST 로고와 Where 라벨의 폰트·크기·두께·색·투명도·테두리를 조정합니다.</p>
        </div>
      </header>

      {loading ? (
        <div className="flex h-40 items-center justify-center text-muted-foreground"><Loader2 className="h-6 w-6 animate-spin" /></div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <TargetPanel
              title="PLAY LIST (메인 로고)"
              sample="PLAY LIST"
              previewScale={0.18}
              value={config.play_list}
              sizeRange={[80, 480]}
              onChange={(p) => patchTarget("play_list", p)}
            />
            <TargetPanel
              title="Where : ___ 라벨"
              sample="Where : Tokyo"
              previewScale={1}
              value={config.where_label}
              sizeRange={[12, 80]}
              onChange={(p) => patchTarget("where_label", p)}
            />
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <button
              type="button"
              onClick={save}
              disabled={saving}
              className="inline-flex items-center justify-center gap-1.5 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-60"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} 저장
            </button>
            <span className="text-xs text-muted-foreground">다음 영상부터 자동 적용. 기존 영상은 <Link href="/music/queue" className="text-primary hover:underline">검토 대기</Link>에서 [재렌더]로 반영하세요.</span>
          </div>
        </>
      )}
    </div>
  )
}

function TargetPanel({
  title, sample, previewScale, value, sizeRange, onChange,
}: {
  title: string
  sample: string
  previewScale: number
  value: TextStyleConfig
  sizeRange: [number, number]
  onChange: (patch: Partial<TextStyleConfig>) => void
}) {
  const stroke = value.border.enabled
    ? { WebkitTextStroke: `${value.border.width}px ${value.border.color}`, paintOrder: "stroke fill" as const }
    : {}

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <h2 className="text-sm font-semibold text-foreground">{title}</h2>

      {/* 미리보기 — 어두운 배경(영상과 유사) */}
      <div className="flex h-40 items-center justify-center overflow-hidden rounded-lg" style={{ background: "#0c1020" }}>
        <span
          style={{
            fontFamily: `"${value.font_family}", sans-serif`,
            fontSize: value.font_size,
            fontWeight: value.font_weight,
            color: value.color,
            opacity: value.opacity,
            letterSpacing: "0.02em",
            whiteSpace: "nowrap",
            transform: `scale(${previewScale})`,
            transformOrigin: "center",
            ...stroke,
          }}
        >
          {sample}
        </span>
      </div>

      {/* 폰트 패밀리 */}
      <Field label="폰트">
        <select
          value={value.font_family}
          onChange={(e) => onChange({ font_family: e.target.value })}
          className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground"
        >
          {DESIGN_PRESET_FONTS.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </Field>

      {/* 크기 */}
      <Field label={`크기 (${value.font_size}px)`}>
        <input
          type="range" min={sizeRange[0]} max={sizeRange[1]} step={1} value={value.font_size}
          onChange={(e) => onChange({ font_size: Number(e.target.value) })}
          className="w-full accent-[var(--color-primary,#a78bfa)]"
        />
      </Field>

      {/* 두께 */}
      <Field label={`두께 (${value.font_weight})`}>
        <select
          value={value.font_weight}
          onChange={(e) => onChange({ font_weight: Number(e.target.value) })}
          className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground"
        >
          {WEIGHTS.map((w) => <option key={w} value={w}>{w}</option>)}
        </select>
      </Field>

      {/* 색상 */}
      <Field label="색상">
        <div className="flex items-center gap-2">
          <input type="color" value={value.color} onChange={(e) => onChange({ color: e.target.value.toUpperCase() })} className="h-9 w-12 rounded border border-border bg-background" />
          <input
            type="text" value={value.color}
            onChange={(e) => onChange({ color: e.target.value })}
            className="h-9 w-28 rounded-md border border-border bg-background px-2 text-sm text-foreground"
          />
        </div>
      </Field>

      {/* 투명도 */}
      <Field label={`투명도 (${Math.round(value.opacity * 100)}%)`}>
        <input
          type="range" min={0} max={100} step={1} value={Math.round(value.opacity * 100)}
          onChange={(e) => onChange({ opacity: Number(e.target.value) / 100 })}
          className="w-full accent-[var(--color-primary,#a78bfa)]"
        />
      </Field>

      {/* 테두리 */}
      <Field label="테두리">
        <div className="flex flex-col gap-2">
          <label className="flex items-center gap-2 text-sm text-foreground">
            <input
              type="checkbox" checked={value.border.enabled}
              onChange={(e) => onChange({ border: { ...value.border, enabled: e.target.checked } })}
            />
            테두리 사용
          </label>
          {value.border.enabled && (
            <div className="flex items-center gap-3">
              <span className="text-xs text-muted-foreground">두께 {value.border.width}px</span>
              <input
                type="range" min={0} max={20} step={1} value={value.border.width}
                onChange={(e) => onChange({ border: { ...value.border, width: Number(e.target.value) } })}
                className="flex-1 accent-[var(--color-primary,#a78bfa)]"
              />
              <input
                type="color" value={value.border.color}
                onChange={(e) => onChange({ border: { ...value.border, color: e.target.value.toUpperCase() } })}
                className="h-8 w-10 rounded border border-border bg-background"
              />
            </div>
          )}
        </div>
      </Field>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}
