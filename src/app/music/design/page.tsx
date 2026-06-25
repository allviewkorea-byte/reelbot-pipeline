"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { ArrowLeft, Loader2, Save, Pencil } from "lucide-react"
import {
  DEFAULT_DESIGN_CONFIG,
  DEFAULT_EQUALIZER,
  DESIGN_PRESET_FONTS,
  DESIGN_PRESET_FONTS_KR,
  DESIGN_FONT_LABELS,
  DESIGN_KR_FONT_DEFAULT,
  DESIGN_TEXT_DEFAULTS,
  type EqualizerConfig,
  type MusicDesignConfig,
  type TextStyleConfig,
} from "@/lib/music"

// 요소 위치 기본값(MusicViz 하드코딩 비율과 동일 → 미설정 시 회귀 0).
const POS_DEFAULTS = {
  logo_x: 0.5, logo_y: 0.5,
  title_x: 0.06, title_y: 0.67,
  subtitle_x: 0.06, subtitle_y: 0.755,
  location_x: 0.5, location_y: 0.04,
} as const
type PosKey = keyof typeof POS_DEFAULTS

// 요소 크기 배율 기본값(1.0 = 100%, 범위 0.5~2.0). 미설정 시 회귀 0.
const SCALE_DEFAULTS = {
  logo_scale: 1, title_scale: 1, subtitle_scale: 1, location_scale: 1,
} as const
type ScaleKey = keyof typeof SCALE_DEFAULTS

// 심경하체 미리보기 @font-face — Google Fonts 미존재라 /public/fonts 번들 TTF 로드(globals.css 무수정).
const SIMGYEONGHA_FACE = `@font-face{font-family:"SimgyeongHa";src:url("/fonts/SimgyeongHa.ttf") format("truetype");font-display:swap;}`

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

  const patchPos = (key: PosKey, value: number) =>
    setConfig((c) => ({ ...c, [key]: value }))

  const patchScale = (key: ScaleKey, value: number) =>
    setConfig((c) => ({ ...c, [key]: value }))

  const patchEq = (patch: Partial<EqualizerConfig>) =>
    setConfig((c) => ({ ...c, equalizer: { ...DEFAULT_EQUALIZER, ...c.equalizer, ...patch } }))

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
          // #E 요소 위치(0~1) + #C 이퀄라이저 설정.
          logo_x: config.logo_x ?? POS_DEFAULTS.logo_x,
          logo_y: config.logo_y ?? POS_DEFAULTS.logo_y,
          title_x: config.title_x ?? POS_DEFAULTS.title_x,
          title_y: config.title_y ?? POS_DEFAULTS.title_y,
          subtitle_x: config.subtitle_x ?? POS_DEFAULTS.subtitle_x,
          subtitle_y: config.subtitle_y ?? POS_DEFAULTS.subtitle_y,
          location_x: config.location_x ?? POS_DEFAULTS.location_x,
          location_y: config.location_y ?? POS_DEFAULTS.location_y,
          // #크기 배율(0.5~2.0).
          logo_scale: config.logo_scale ?? SCALE_DEFAULTS.logo_scale,
          title_scale: config.title_scale ?? SCALE_DEFAULTS.title_scale,
          subtitle_scale: config.subtitle_scale ?? SCALE_DEFAULTS.subtitle_scale,
          location_scale: config.location_scale ?? SCALE_DEFAULTS.location_scale,
          equalizer: config.equalizer ?? DEFAULT_EQUALIZER,
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
      {/* 심경하체 미리보기 폰트(번들 TTF) — globals.css 무수정, 컴포넌트 스코프 주입. */}
      <style dangerouslySetInnerHTML={{ __html: SIMGYEONGHA_FACE }} />
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

          {/* #E 레이아웃(위치 조정) — 16:9 미리보기 + 요소별 X/Y 슬라이더 */}
          <LayoutSection config={config} onPos={patchPos} onScale={patchScale} />

          {/* #C 이퀄라이저(산 모양, 로고 위) 설정 */}
          <EqualizerSection eq={{ ...DEFAULT_EQUALIZER, ...config.equalizer }} onChange={patchEq} />

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
            {DESIGN_PRESET_FONTS_KR.map((f) => <option key={f} value={f}>{DESIGN_FONT_LABELS[f] ?? f}</option>)}
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

// 두 hex 색 선형 보간(미리보기 막대별 색) — Remotion mixHex 와 동일 규칙.
function mixHex(a: string, b: string, t: number): string {
  const p = (h: string) => {
    const m = /^#?([0-9a-f]{6})$/i.exec(h.trim())
    const n = m ? parseInt(m[1], 16) : 0
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
  }
  const [r1, g1, b1] = p(a)
  const [r2, g2, b2] = p(b)
  const k = Math.max(0, Math.min(1, t))
  const ch = (x: number, y: number) => Math.round(x + (y - x) * k)
  return `rgb(${ch(r1, r2)}, ${ch(g1, g2)}, ${ch(b1, b2)})`
}

// #E 레이아웃 — 16:9 미리보기 + 요소별 X/Y 슬라이더(실시간 반영).
function LayoutSection({ config, onPos, onScale }: {
  config: MusicDesignConfig
  onPos: (key: PosKey, value: number) => void
  onScale: (key: ScaleKey, value: number) => void
}) {
  const at = (k: PosKey) => config[k] ?? POS_DEFAULTS[k]
  const sc = (k: ScaleKey) => config[k] ?? SCALE_DEFAULTS[k]
  const eq = { ...DEFAULT_EQUALIZER, ...config.equalizer }
  const elements: { label: string; xk: PosKey; yk: PosKey; sk: ScaleKey; center: boolean; cls: string }[] = [
    { label: (config.playlist_text || "PLAY LIST"), xk: "logo_x", yk: "logo_y", sk: "logo_scale", center: true, cls: "text-base font-bold text-white" },
    { label: (config.preview_title || "제목"), xk: "title_x", yk: "title_y", sk: "title_scale", center: false, cls: "text-xs text-white/90" },
    { label: (config.preview_subtitle || "부제목"), xk: "subtitle_x", yk: "subtitle_y", sk: "subtitle_scale", center: false, cls: "text-[10px] italic text-white/70" },
    { label: "Tokyo", xk: "location_x", yk: "location_y", sk: "location_scale", center: true, cls: "text-[10px] tracking-wide text-white/80" },
  ]
  // 미리보기 이퀄(로고 바로 위) — 오디오 반응 형태를 흉내낸 비대칭 막대(산 모양 고정 아님), pill.
  const eqBars = Array.from({ length: 20 }, (_, i) => 0.32 + 0.6 * Math.abs(Math.sin(i * 1.7 + 0.5)))
  return (
    <section className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <h2 className="text-sm font-semibold text-foreground">레이아웃 (위치·크기 조정) · 16:9 미리보기</h2>
      <div className="relative w-full overflow-hidden rounded-lg" style={{ aspectRatio: "16 / 9", background: "#0c1020" }}>
        {/* 로고 위 이퀄 미리보기(오디오 반응형 · pill) */}
        <div
          className="absolute flex items-end justify-center"
          style={{
            left: `${at("logo_x") * 100}%`,
            top: `${at("logo_y") * 100}%`,
            transform: "translate(-50%, calc(-50% - 1.4em))",
            width: `${(eq.width / 1920) * 100}%`,
            height: `${(eq.max_height / 1080) * 100}%`,
            gap: 2,
          }}
        >
          {eqBars.map((v, i) => {
            const tCol = eq.gradient === "center" ? Math.abs(i / 19 - 0.5) * 2 : i / 19
            return <div key={i} style={{ flex: 1, height: `${Math.max(12, v * 100)}%`, borderRadius: 9999, background: mixHex(eq.color1, eq.color2, tCol) }} />
          })}
        </div>
        {elements.map((el) => (
          <span
            key={el.xk}
            className={`absolute whitespace-nowrap ${el.cls}`}
            style={{
              left: `${at(el.xk) * 100}%`,
              top: `${at(el.yk) * 100}%`,
              transform: `${el.center ? "translate(-50%, -50%)" : "translateY(-50%)"} scale(${sc(el.sk)})`,
              transformOrigin: el.center ? "center" : "left center",
            }}
          >
            {el.label}
          </span>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {elements.map((el) => (
          <div key={el.xk} className="flex flex-col gap-1 rounded-lg border border-border/60 p-2">
            <span className="text-xs font-medium text-foreground">{el.label}</span>
            <Field label={`X (${Math.round(at(el.xk) * 100)}%)`}>
              <input type="range" min={0} max={100} step={1} value={Math.round(at(el.xk) * 100)}
                onChange={(e) => onPos(el.xk, Number(e.target.value) / 100)}
                className="w-full accent-[var(--color-primary,#a78bfa)]" />
            </Field>
            <Field label={`Y (${Math.round(at(el.yk) * 100)}%)`}>
              <input type="range" min={0} max={100} step={1} value={Math.round(at(el.yk) * 100)}
                onChange={(e) => onPos(el.yk, Number(e.target.value) / 100)}
                className="w-full accent-[var(--color-primary,#a78bfa)]" />
            </Field>
            <Field label={`크기 (${Math.round(sc(el.sk) * 100)}%)`}>
              <input type="range" min={50} max={200} step={1} value={Math.round(sc(el.sk) * 100)}
                onChange={(e) => onScale(el.sk, Number(e.target.value) / 100)}
                className="w-full accent-[var(--color-primary,#a78bfa)]" />
            </Field>
          </div>
        ))}
      </div>
    </section>
  )
}

// #C 이퀄라이저 설정 — 색상·그라데이션·사이즈·로고 위 간격.
function EqualizerSection({ eq, onChange }: {
  eq: EqualizerConfig
  onChange: (patch: Partial<EqualizerConfig>) => void
}) {
  const bars = Array.from({ length: 20 }, (_, i) => 0.32 + 0.6 * Math.abs(Math.sin(i * 1.7 + 0.5)))
  return (
    <section className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <h2 className="text-sm font-semibold text-foreground">이퀄라이저 (오디오 반응 · pill · 로고 위)</h2>
      {/* 미리보기 막대(오디오 반응형 · pill 끝) */}
      <div className="flex h-24 items-end justify-center gap-1 overflow-hidden rounded-lg" style={{ background: "#0c1020" }}>
        {bars.map((v, i) => {
          const tCol = eq.gradient === "center" ? Math.abs(i / 19 - 0.5) * 2 : i / 19
          return <div key={i} style={{ width: 8, height: `${Math.max(11, v * 90)}%`, borderRadius: 9999, background: mixHex(eq.color1, eq.color2, tCol) }} />
        })}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="색상 1 (시작)">
          <div className="flex items-center gap-2">
            <input type="color" value={eq.color1} onChange={(e) => onChange({ color1: e.target.value.toUpperCase() })} className="h-9 w-12 rounded border border-border bg-background" />
            <input type="text" value={eq.color1} onChange={(e) => onChange({ color1: e.target.value })} className="h-9 w-28 rounded-md border border-border bg-background px-2 text-sm text-foreground" />
          </div>
        </Field>
        <Field label="색상 2 (끝)">
          <div className="flex items-center gap-2">
            <input type="color" value={eq.color2} onChange={(e) => onChange({ color2: e.target.value.toUpperCase() })} className="h-9 w-12 rounded border border-border bg-background" />
            <input type="text" value={eq.color2} onChange={(e) => onChange({ color2: e.target.value })} className="h-9 w-28 rounded-md border border-border bg-background px-2 text-sm text-foreground" />
          </div>
        </Field>
        <Field label="그라데이션 방향">
          <select value={eq.gradient} onChange={(e) => onChange({ gradient: e.target.value as EqualizerConfig["gradient"] })}
            className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground">
            <option value="horizontal">좌 → 우</option>
            <option value="center">가운데 → 바깥</option>
          </select>
        </Field>
        <Field label={`높이 max (${eq.max_height}px)`}>
          <input type="range" min={20} max={400} step={1} value={eq.max_height}
            onChange={(e) => onChange({ max_height: Number(e.target.value) })}
            className="w-full accent-[var(--color-primary,#a78bfa)]" />
        </Field>
        <Field label={`너비 (${eq.width}px)`}>
          <input type="range" min={100} max={1920} step={10} value={eq.width}
            onChange={(e) => onChange({ width: Number(e.target.value) })}
            className="w-full accent-[var(--color-primary,#a78bfa)]" />
        </Field>
        <Field label={`로고 위 간격 (${eq.gap_above_logo}px)`}>
          <input type="range" min={0} max={600} step={1} value={eq.gap_above_logo}
            onChange={(e) => onChange({ gap_above_logo: Number(e.target.value) })}
            className="w-full accent-[var(--color-primary,#a78bfa)]" />
        </Field>
      </div>
    </section>
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
