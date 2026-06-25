"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { ArrowLeft, Loader2, Save, Pencil } from "lucide-react"
import {
  DEFAULT_DESIGN_CONFIG,
  DESIGN_PRESET_FONTS,
  DESIGN_PRESET_FONTS_KR,
  DESIGN_KR_FONT_DEFAULT,
  DESIGN_TEXT_DEFAULTS,
  type MusicDesignConfig,
  type TextStyleConfig,
} from "@/lib/music"

// 인라인 편집 텍스트 필드 키 / 스타일(TextStyleConfig) 대상 키.
type TextKey = "playlist_text" | "where_text" | "preview_title" | "preview_subtitle"
type StyleKey = "play_list" | "where_label" | "title" | "subtitle"

// 미리보기용 Google Fonts(프리셋 10종) — Remotion 렌더와 동일 패밀리. 가중치는 기본 로드(미리보기는 faux-bold 허용).
const FONT_LINK =
  "https://fonts.googleapis.com/css2?" +
  [...DESIGN_PRESET_FONTS, ...DESIGN_PRESET_FONTS_KR].map((f) => "family=" + f.replace(/ /g, "+")).join("&") +
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

  const patchTarget = (target: StyleKey, patch: Partial<TextStyleConfig>) =>
    setConfig((c) => ({ ...c, [target]: { ...c[target], ...patch } }))

  const patchText = (key: TextKey, value: string) =>
    setConfig((c) => ({ ...c, [key]: value }))

  const save = useCallback(async () => {
    setSaving(true)
    try {
      const res = await fetch("/api/music/design-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          play_list: config.play_list,
          where_label: config.where_label,
          // 인라인 편집 텍스트(빈값=기본값). playlist/where 는 영상 반영, preview_* 는 미리보기 전용.
          playlist_text: config.playlist_text ?? "",
          where_text: config.where_text ?? "",
          where_label_hidden: config.where_label_hidden ?? true,
          title_font_kr: config.title_font_kr ?? DESIGN_KR_FONT_DEFAULT,
          subtitle_font_kr: config.subtitle_font_kr ?? DESIGN_KR_FONT_DEFAULT,
          preview_title: config.preview_title ?? "",
          preview_subtitle: config.preview_subtitle ?? "",
        }),
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
              title="메인 로고"
              textValue={config.playlist_text ?? ""}
              textDefault={DESIGN_TEXT_DEFAULTS.playlist_text}
              onTextChange={(v) => patchText("playlist_text", v)}
              previewScale={0.18}
              value={config.play_list}
              sizeRange={[80, 480]}
              onChange={(p) => patchTarget("play_list", p)}
            />
            <TargetPanel
              title="Where : ___ 라벨"
              textValue={config.where_text ?? ""}
              textDefault={DESIGN_TEXT_DEFAULTS.where_text}
              textSuffix=" : Tokyo"
              onTextChange={(v) => patchText("where_text", v)}
              previewScale={1}
              value={config.where_label}
              sizeRange={[12, 80]}
              onChange={(p) => patchTarget("where_label", p)}
              hidden={config.where_label_hidden ?? true}
              onHiddenChange={(v) => setConfig((c) => ({ ...c, where_label_hidden: v }))}
            />
            <TargetPanel
              title="제목 (곡 제목 · 미리보기 전용)"
              textValue={config.preview_title ?? ""}
              textDefault={DESIGN_TEXT_DEFAULTS.preview_title}
              onTextChange={(v) => patchText("preview_title", v)}
              previewScale={0.6}
              withItalic
              value={config.title}
              sizeRange={[24, 160]}
              onChange={(p) => patchTarget("title", p)}
              krFont={config.title_font_kr ?? DESIGN_KR_FONT_DEFAULT}
              onKrFontChange={(v) => setConfig((c) => ({ ...c, title_font_kr: v }))}
            />
            <TargetPanel
              title="부제목 (미리보기 전용)"
              textValue={config.preview_subtitle ?? ""}
              textDefault={DESIGN_TEXT_DEFAULTS.preview_subtitle}
              onTextChange={(v) => patchText("preview_subtitle", v)}
              previewScale={0.7}
              withItalic
              value={config.subtitle}
              sizeRange={[16, 120]}
              onChange={(p) => patchTarget("subtitle", p)}
              krFont={config.subtitle_font_kr ?? DESIGN_KR_FONT_DEFAULT}
              onKrFontChange={(v) => setConfig((c) => ({ ...c, subtitle_font_kr: v }))}
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

// 인라인 편집 텍스트 — 클릭하면 contentEditable 로 편집. 엔터/바깥클릭=저장, ESC=취소.
// 편집 중에는 React 가 내용을 제어하지 않고(uncontrolled), ref 로 textContent 를 다룬다(커서 점프 방지).
function EditableText({ value, placeholder, onCommit }: {
  value: string
  placeholder: string
  onCommit: (value: string) => void
}) {
  const ref = useRef<HTMLSpanElement>(null)
  const [editing, setEditing] = useState(false)

  const start = () => {
    if (editing) return
    setEditing(true)
    requestAnimationFrame(() => {
      const el = ref.current
      if (!el) return
      el.textContent = value
      el.focus()
      const range = document.createRange()
      range.selectNodeContents(el)
      const sel = window.getSelection()
      sel?.removeAllRanges()
      sel?.addRange(range)
    })
  }
  const commit = () => {
    setEditing(false)
    onCommit((ref.current?.textContent ?? "").trim())
  }
  const cancel = () => setEditing(false) // onCommit 미호출 → 원래 값 복원(React 재렌더)

  return (
    <span
      ref={ref}
      role="textbox"
      tabIndex={0}
      contentEditable={editing}
      suppressContentEditableWarning
      onClick={start}
      onFocus={start}
      onBlur={() => { if (editing) commit() }}
      onKeyDown={(e) => {
        if (e.key === "Enter") { e.preventDefault(); ref.current?.blur() }
        else if (e.key === "Escape") { e.preventDefault(); cancel(); ref.current?.blur() }
      }}
      style={{
        cursor: editing ? "text" : "pointer",
        outline: editing ? "1px dashed rgba(255,255,255,0.6)" : "none",
        outlineOffset: 4,
        borderRadius: 2,
        minWidth: "1ch",
        // 빈 값(기본 텍스트)도 부모 색(흰색)을 그대로 사용 — 미리보기 100% 흰색.
      }}
    >
      {editing ? null : (value || placeholder)}
    </span>
  )
}

function TargetPanel({
  title, textValue, textDefault, textSuffix = "", onTextChange,
  previewScale, value, sizeRange, onChange, withItalic = false,
  hidden, onHiddenChange, krFont, onKrFontChange,
}: {
  title: string
  textValue: string
  textDefault: string
  textSuffix?: string
  onTextChange: (value: string) => void
  previewScale: number
  value: TextStyleConfig
  sizeRange: [number, number]
  onChange: (patch: Partial<TextStyleConfig>) => void
  withItalic?: boolean
  hidden?: boolean
  onHiddenChange?: (value: boolean) => void
  krFont?: string
  onKrFontChange?: (value: string) => void
}) {
  const stroke = value.border.enabled
    ? { WebkitTextStroke: `${value.border.width}px ${value.border.color}`, paintOrder: "stroke fill" as const }
    : {}

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <h2 className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
        {title}
        <span className="inline-flex items-center gap-0.5 text-[11px] font-normal text-muted-foreground"><Pencil className="h-3 w-3" /> 텍스트 클릭 편집</span>
      </h2>

      {/* 미리보기 — 어두운 배경(영상과 유사). 텍스트 클릭 → 인라인 편집. */}
      <div className="flex h-40 items-center justify-center overflow-hidden rounded-lg" style={{ background: "#0c1020" }}>
        <div
          style={{
            display: "inline-flex",
            alignItems: "baseline",
            // 영어+한글 스택(한글 폰트 패널이 있으면 fallback 적용). 없으면 기존과 동일.
            fontFamily: onKrFontChange
              ? `"${value.font_family}", "${krFont ?? DESIGN_KR_FONT_DEFAULT}", sans-serif`
              : `"${value.font_family}", sans-serif`,
            fontSize: value.font_size,
            fontWeight: value.font_weight,
            fontStyle: withItalic && value.italic ? "italic" : "normal",
            color: value.color,
            opacity: value.opacity,
            letterSpacing: "0.02em",
            whiteSpace: "nowrap",
            transform: `scale(${previewScale})`,
            transformOrigin: "center",
            ...stroke,
          }}
        >
          <EditableText value={textValue} placeholder={textDefault} onCommit={onTextChange} />
          {textSuffix && <span>{textSuffix}</span>}
        </div>
      </div>

      {/* 영상에서 라벨 숨김(Where 전용) — 체크 시 영상에 렌더 안 함(기본 체크). */}
      {onHiddenChange && (
        <label className="flex items-center gap-2 text-sm text-foreground">
          <input
            type="checkbox" checked={!!hidden}
            onChange={(e) => onHiddenChange(e.target.checked)}
          />
          영상에서 사용 안 함 (숨김)
        </label>
      )}

      {/* 폰트 패밀리(영어) */}
      <Field label={onKrFontChange ? "영어 폰트" : "폰트"}>
        <select
          value={value.font_family}
          onChange={(e) => onChange({ font_family: e.target.value })}
          className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground"
        >
          {DESIGN_PRESET_FONTS.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </Field>

      {/* 한글 폰트(제목·부제만) — 영어 폰트 뒤 스택. 한글 글자가 이 폰트로 렌더된다. */}
      {onKrFontChange && (
        <Field label="한글 폰트">
          <select
            value={krFont ?? DESIGN_KR_FONT_DEFAULT}
            onChange={(e) => onKrFontChange(e.target.value)}
            className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground"
          >
            {DESIGN_PRESET_FONTS_KR.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </Field>
      )}

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

      {/* 기울임(제목·부제만) */}
      {withItalic && (
        <label className="flex items-center gap-2 text-sm text-foreground">
          <input
            type="checkbox" checked={!!value.italic}
            onChange={(e) => onChange({ italic: e.target.checked })}
          />
          기울임 (italic)
        </label>
      )}

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
