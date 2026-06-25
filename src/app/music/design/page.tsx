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

// 미리보기용 Google Fonts — 패밀리별 '지원 weight' 를 함께 요청해야 두께가 실제로 반영된다
// (weight 축 없이 요청하면 400만 로드돼 두께 변경이 미반영). 단일 weight 폰트는 축 생략.
// 잘못된 weight 가 섞이면 해당 패밀리 요청만 실패하도록 패밀리당 <link> 를 분리한다.
const FONT_WGHT: Record<string, string> = {
  Montserrat: "100;200;300;400;500;600;700;800;900",
  Poppins: "100;200;300;400;500;600;700;800;900",
  Oswald: "200;300;400;500;600;700",
  Archivo: "100;200;300;400;500;600;700;800;900",
  Inter: "100;200;300;400;500;600;700;800;900",
  "DM Sans": "100;200;300;400;500;600;700;800;900",
  "Playfair Display": "400;500;600;700;800;900",
  "Cormorant Garamond": "300;400;500;600;700",
  "Bodoni Moda": "400;500;600;700;800;900",
  Literata: "200;300;400;500;600;700;800;900",
  "Noto Serif KR": "200;300;400;500;600;700;900",
  "Nanum Myeongjo": "400;700;800",
  // 단일 weight(축 생략): Bebas Neue, Anton, Young Serif, Black Han Sans
}
const PREVIEW_FONT_LINKS = [...DESIGN_PRESET_FONTS, ...DESIGN_PRESET_FONTS_KR].map((f) => {
  const fam = f.replace(/ /g, "+")
  const w = FONT_WGHT[f]
  return `https://fonts.googleapis.com/css2?family=${fam}${w ? `:wght@${w}` : ""}&display=swap`
})

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
          logo_underline_weight: config.logo_underline_weight ?? 2,
          location_letter_spacing: config.location_letter_spacing ?? 0,
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
    <div className="flex h-full min-h-0 flex-col overflow-auto">
      {PREVIEW_FONT_LINKS.map((href) => <link key={href} rel="stylesheet" href={href} />)}
      {/* 심경하체 미리보기 폰트(번들 TTF) — globals.css 무수정, 컴포넌트 스코프 주입. */}
      <style dangerouslySetInnerHTML={{ __html: SIMGYEONGHA_FACE }} />

      {loading ? (
        <div className="flex h-40 items-center justify-center text-muted-foreground"><Loader2 className="h-6 w-6 animate-spin" /></div>
      ) : (
        <>
          {/* 상단 고정 미리보기 — 스크롤해도 항상 보임. 모든 설정(폰트·크기·색·위치·이퀄) 실시간 반영. */}
          <div className="sticky top-0 z-20 border-b border-border bg-background/95 px-4 pb-3 pt-3 backdrop-blur md:px-6">
            <div className="mb-2 flex items-center gap-3 pl-10 md:pl-0">
              <Link href="/music" className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-white/5 hover:text-foreground">
                <ArrowLeft className="h-4 w-4" /> 대시보드
              </Link>
              <div className="min-w-0 flex-1">
                <h1 className="text-base font-semibold text-foreground">디자인 본부</h1>
                <p className="truncate text-xs text-muted-foreground">아래 컨트롤의 모든 설정이 이 미리보기에 실시간 반영됩니다.</p>
              </div>
              <button
                type="button"
                onClick={save}
                disabled={saving}
                className="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-60"
              >
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} 저장
              </button>
            </div>
            <UnifiedPreview config={config} />
          </div>

          {/* 하단 컨트롤(스크롤 영역) — 각 패널은 미리보기 없이 컴팩트. */}
          <div className="flex flex-col gap-4 p-4 md:p-6">
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              <TargetPanel
                title="메인 로고"
                textValue={config.playlist_text ?? ""}
                textDefault={DESIGN_TEXT_DEFAULTS.playlist_text}
                onTextChange={(v) => patchText("playlist_text", v)}
                value={config.play_list}
                sizeRange={[80, 1200]}
                onChange={(p) => patchTarget("play_list", p)}
                underlineWeight={config.logo_underline_weight ?? 2}
                onUnderlineWeight={(v) => setConfig((c) => ({ ...c, logo_underline_weight: v }))}
              />
              <TargetPanel
                title="라벨"
                textValue={config.where_text ?? ""}
                textDefault={DESIGN_TEXT_DEFAULTS.where_text}
                onTextChange={(v) => patchText("where_text", v)}
                value={config.where_label}
                sizeRange={[12, 240]}
                onChange={(p) => patchTarget("where_label", p)}
                hidden={config.where_label_hidden ?? true}
                onHiddenChange={(v) => setConfig((c) => ({ ...c, where_label_hidden: v }))}
                letterSpacing={config.location_letter_spacing ?? 0}
                onLetterSpacing={(v) => setConfig((c) => ({ ...c, location_letter_spacing: v }))}
              />
              <TargetPanel
                title="제목 (곡 제목 · 미리보기 전용)"
                textValue={config.preview_title ?? ""}
                textDefault={DESIGN_TEXT_DEFAULTS.preview_title}
                onTextChange={(v) => patchText("preview_title", v)}
                withItalic
                value={config.title}
                sizeRange={[24, 480]}
                onChange={(p) => patchTarget("title", p)}
                krFont={config.title_font_kr ?? DESIGN_KR_FONT_DEFAULT}
                onKrFontChange={(v) => setConfig((c) => ({ ...c, title_font_kr: v }))}
              />
              <TargetPanel
                title="부제목 (미리보기 전용)"
                textValue={config.preview_subtitle ?? ""}
                textDefault={DESIGN_TEXT_DEFAULTS.preview_subtitle}
                onTextChange={(v) => patchText("preview_subtitle", v)}
                withItalic
                value={config.subtitle}
                sizeRange={[16, 360]}
                onChange={(p) => patchTarget("subtitle", p)}
                krFont={config.subtitle_font_kr ?? DESIGN_KR_FONT_DEFAULT}
                onKrFontChange={(v) => setConfig((c) => ({ ...c, subtitle_font_kr: v }))}
              />
            </div>

            {/* 레이아웃(위치·크기 슬라이더) — 미리보기는 상단 통합 미리보기로 대체. */}
            <LayoutControls config={config} onPos={patchPos} onScale={patchScale} />

            {/* 이퀄라이저 설정(색·그라데이션·사이즈) — 미리보기는 상단 통합 미리보기로 대체. */}
            <EqualizerControls eq={{ ...DEFAULT_EQUALIZER, ...config.equalizer }} onChange={patchEq} />

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
      // 타이핑 즉시 상위 상태(→ 미리보기) 반영. editing 중엔 children=null 이라 DOM 텍스트
      // 미초기화 → 커서 점프 없음. blur 시 commit() 가 최종 trim 값으로 마무리.
      onInput={() => onCommit(ref.current?.textContent ?? "")}
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
  value, sizeRange, onChange, withItalic = false,
  hidden, onHiddenChange, krFont, onKrFontChange,
  underlineWeight, onUnderlineWeight,
  letterSpacing, onLetterSpacing,
}: {
  title: string
  textValue: string
  textDefault: string
  textSuffix?: string
  onTextChange: (value: string) => void
  value: TextStyleConfig
  sizeRange: [number, number]
  onChange: (patch: Partial<TextStyleConfig>) => void
  withItalic?: boolean
  hidden?: boolean
  onHiddenChange?: (value: boolean) => void
  krFont?: string
  onKrFontChange?: (value: string) => void
  underlineWeight?: number
  onUnderlineWeight?: (value: number) => void
  letterSpacing?: number
  onLetterSpacing?: (value: number) => void
}) {
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3">
      <h2 className="text-sm font-semibold text-foreground">{title}</h2>

      {/* 텍스트(클릭 편집) — 시각 미리보기는 상단 통합 미리보기에 반영. */}
      <Field label={<span className="inline-flex items-center gap-0.5">텍스트 <Pencil className="h-3 w-3" /> 클릭 편집</span>}>
        <div className="flex min-h-9 items-center rounded-md border border-border bg-background px-2 text-sm text-foreground">
          <EditableText value={textValue} placeholder={textDefault} onCommit={onTextChange} />
          {textSuffix && <span className="text-muted-foreground">{textSuffix}</span>}
        </div>
      </Field>

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

      {/* 밑줄 두께(메인 로고만) — '_' 문자를 실제 선으로 렌더, 선 굵기(px) 조절. */}
      {onUnderlineWeight && (
        <Field label={`밑줄 두께(px) (${underlineWeight ?? 2})`}>
          <input
            type="range" min={0.5} max={20} step={0.5} value={underlineWeight ?? 2}
            onChange={(e) => onUnderlineWeight(Number(e.target.value))}
            className="w-full accent-[var(--color-primary,#a78bfa)]"
          />
        </Field>
      )}

      {/* 글자 간격(라벨만) */}
      {onLetterSpacing && (
        <Field label={`글자 간격 (${letterSpacing ?? 0}px)`}>
          <input
            type="range" min={-10} max={50} step={1} value={letterSpacing ?? 0}
            onChange={(e) => onLetterSpacing(Number(e.target.value))}
            className="w-full accent-[var(--color-primary,#a78bfa)]"
          />
        </Field>
      )}

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

// 테두리(외곽선) 스타일 — Remotion strokeStyle 과 동일 규칙(미리보기 반영).
function strokeOf(b: TextStyleConfig["border"]): React.CSSProperties {
  return b.enabled ? { WebkitTextStroke: `${b.width}px ${b.color}`, paintOrder: "stroke fill" } : {}
}

// 로고 텍스트를 '_'(밑줄) 런 단위로 분할 — '_' 문자에는 밑줄 두께를 따로 적용(나머지는 로고 두께).
function logoRuns(text: string): { s: string; underline: boolean }[] {
  const runs: { s: string; underline: boolean }[] = []
  for (const ch of text) {
    const u = ch === "_"
    const last = runs[runs.length - 1]
    if (last && last.underline === u) last.s += ch
    else runs.push({ s: ch, underline: u })
  }
  return runs
}

// 상단 통합 16:9 미리보기 — 영상(MusicViz)과 같은 결로 모든 요소를 그린다.
// 폰트는 cqw(컨테이너 너비 %) 로 1920px 캔버스 기준 크기를 비례 환산 → 박스 크기와 무관하게 정확.
function UnifiedPreview({ config }: { config: MusicDesignConfig }) {
  const W = 1920, H = 1080
  const cqw = (px: number) => `${(px / W) * 100}cqw`
  const pos = (k: PosKey) => config[k] ?? POS_DEFAULTS[k]
  const scl = (k: ScaleKey) => config[k] ?? SCALE_DEFAULTS[k]
  const eq = { ...DEFAULT_EQUALIZER, ...config.equalizer }
  const logo = config.play_list, ti = config.title, su = config.subtitle, wl = config.where_label
  const krTitle = config.title_font_kr ?? DESIGN_KR_FONT_DEFAULT
  const krSub = config.subtitle_font_kr ?? DESIGN_KR_FONT_DEFAULT
  const shadow = "0 2px 14px rgba(0,0,0,0.78)"
  // 이퀄 세로 위치: 로고 윗변 - 로고위간격 - 이퀄높이 (영상 계산과 동일 결).
  const eqHFrac = eq.max_height / H
  const eqTopFrac = pos("logo_y") - (logo.font_size * scl("logo_scale") / 2) / H - eq.gap_above_logo / H - eqHFrac
  const eqBars = Array.from({ length: 20 }, (_, i) => 0.32 + 0.6 * Math.abs(Math.sin(i * 1.7 + 0.5)))
  const showLoc = !(config.where_label_hidden ?? true)
  return (
    <div
      className="relative mx-auto w-full overflow-hidden rounded-lg"
      style={{ aspectRatio: "16 / 9", maxHeight: 360, maxWidth: 640, containerType: "inline-size", background: "#0c1020" }}
    >
      {/* 하단 가독성 스크림 */}
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: "42%", background: "linear-gradient(to top, rgba(0,0,0,0.45), rgba(0,0,0,0))" }} />

      {/* 이퀄(로고 위, pill · 오디오 반응형 표현) */}
      <div
        className="absolute flex items-end justify-center"
        style={{ left: `${(eq.x ?? 0.5) * 100}%`, top: `${eqTopFrac * 100}%`, width: `${(eq.width / W) * 100}%`, height: `${eqHFrac * 100}%`, transform: "translateX(-50%)", gap: 2 }}
      >
        {eqBars.map((v, i) => {
          const tCol = eq.gradient === "center" ? Math.abs(i / 19 - 0.5) * 2 : i / 19
          return <div key={i} style={{ flex: 1, height: `${Math.max(12, v * 100)}%`, borderRadius: 9999, background: mixHex(eq.color1, eq.color2, tCol) }} />
        })}
      </div>

      {/* 메인 로고 — '_'(밑줄) 문자만 별도 두께(logo_underline_weight) 적용. */}
      <div style={{
        position: "absolute", left: `${pos("logo_x") * 100}%`, top: `${pos("logo_y") * 100}%`,
        transform: `translate(-50%, -50%) scale(${scl("logo_scale")})`,
        fontFamily: `"${logo.font_family}", sans-serif`, fontSize: cqw(logo.font_size), fontWeight: logo.font_weight,
        color: logo.color, opacity: logo.opacity, lineHeight: 1, whiteSpace: "nowrap", textShadow: shadow, ...strokeOf(logo.border),
      }}>{logoRuns(config.playlist_text || DESIGN_TEXT_DEFAULTS.playlist_text).map((r, i) => r.underline ? (
        // '_' 런 → 실제 가로 선(굵기 px). 투명 언더스코어로 동일 너비 확보. 굵기는 cqw 로 환산(영상과 비례).
        <span key={i} style={{ position: "relative", display: "inline-block", color: "transparent", whiteSpace: "pre" }}>
          {r.s}
          <span style={{ position: "absolute", left: 0, right: 0, bottom: "0.1em", height: cqw(config.logo_underline_weight ?? 2), borderRadius: 9999, background: logo.color }} />
        </span>
      ) : (
        <span key={i}>{r.s}</span>
      ))}</div>

      {/* 제목(좌하단, 영어+한글 스택) */}
      <div style={{
        position: "absolute", left: `${pos("title_x") * 100}%`, top: `${pos("title_y") * 100}%`,
        transform: `scale(${scl("title_scale")})`, transformOrigin: "left top",
        fontFamily: `"${ti.font_family}", "${krTitle}", sans-serif`, fontSize: cqw(ti.font_size), fontWeight: ti.font_weight,
        fontStyle: ti.italic ? "italic" : "normal", color: ti.color, opacity: ti.opacity, whiteSpace: "nowrap", textShadow: shadow, ...strokeOf(ti.border),
      }}>{config.preview_title || DESIGN_TEXT_DEFAULTS.preview_title}</div>

      {/* 부제목(좌하단, 영어+한글 스택) */}
      <div style={{
        position: "absolute", left: `${pos("subtitle_x") * 100}%`, top: `${pos("subtitle_y") * 100}%`,
        transform: `scale(${scl("subtitle_scale")})`, transformOrigin: "left top",
        fontFamily: `"${su.font_family}", "${krSub}", sans-serif`, fontSize: cqw(su.font_size), fontWeight: su.font_weight,
        fontStyle: su.italic ? "italic" : "normal", color: su.color, opacity: su.opacity, whiteSpace: "nowrap", textShadow: shadow, ...strokeOf(su.border),
      }}>{config.preview_subtitle || DESIGN_TEXT_DEFAULTS.preview_subtitle}</div>

      {/* 라벨(숨김이 아닐 때만) — 입력값 그대로 표시(접두사 없음). */}
      {showLoc && (
        <div style={{
          position: "absolute", left: `${pos("location_x") * 100}%`, top: `${pos("location_y") * 100}%`,
          transform: `translateX(-50%) scale(${scl("location_scale")})`, transformOrigin: "center top",
          fontFamily: `"${wl.font_family}", sans-serif`, fontSize: cqw(wl.font_size), fontWeight: wl.font_weight,
          color: wl.color, opacity: wl.opacity, letterSpacing: `${config.location_letter_spacing ?? 0}px`, whiteSpace: "nowrap", textShadow: "0 2px 12px rgba(0,0,0,0.8)", ...strokeOf(wl.border),
        }}>{(config.where_text || "").trim() || DESIGN_TEXT_DEFAULTS.where_text}</div>
      )}
    </div>
  )
}

// 레이아웃 컨트롤 — 요소별 X/Y/크기 슬라이더(미리보기는 상단 통합 미리보기).
function LayoutControls({ config, onPos, onScale }: {
  config: MusicDesignConfig
  onPos: (key: PosKey, value: number) => void
  onScale: (key: ScaleKey, value: number) => void
}) {
  const at = (k: PosKey) => config[k] ?? POS_DEFAULTS[k]
  const sc = (k: ScaleKey) => config[k] ?? SCALE_DEFAULTS[k]
  const elements: { label: string; xk: PosKey; yk: PosKey; sk: ScaleKey }[] = [
    { label: "메인 로고", xk: "logo_x", yk: "logo_y", sk: "logo_scale" },
    { label: "제목", xk: "title_x", yk: "title_y", sk: "title_scale" },
    { label: "부제목", xk: "subtitle_x", yk: "subtitle_y", sk: "subtitle_scale" },
    { label: "지역명", xk: "location_x", yk: "location_y", sk: "location_scale" },
  ]
  return (
    <section className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3">
      <h2 className="text-sm font-semibold text-foreground">레이아웃 (위치·크기)</h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {elements.map((el) => (
          <div key={el.xk} className="flex flex-col gap-1 rounded-lg border border-border/60 p-2">
            <span className="text-xs font-medium text-foreground">{el.label}</span>
            <Field label={`X (${Math.round(at(el.xk) * 100)}%)`}>
              <input type="range" min={-20} max={120} step={1} value={Math.round(at(el.xk) * 100)}
                onChange={(e) => onPos(el.xk, Number(e.target.value) / 100)}
                className="w-full accent-[var(--color-primary,#a78bfa)]" />
            </Field>
            <Field label={`Y (${Math.round(at(el.yk) * 100)}%)`}>
              <input type="range" min={-20} max={120} step={1} value={Math.round(at(el.yk) * 100)}
                onChange={(e) => onPos(el.yk, Number(e.target.value) / 100)}
                className="w-full accent-[var(--color-primary,#a78bfa)]" />
            </Field>
            <Field label={`크기 (${Math.round(sc(el.sk) * 100)}%)`}>
              <input type="range" min={50} max={500} step={1} value={Math.round(sc(el.sk) * 100)}
                onChange={(e) => onScale(el.sk, Number(e.target.value) / 100)}
                className="w-full accent-[var(--color-primary,#a78bfa)]" />
            </Field>
          </div>
        ))}
      </div>
    </section>
  )
}

// 이퀄라이저 컨트롤 — 색상·그라데이션·사이즈(미리보기는 상단 통합 미리보기).
function EqualizerControls({ eq, onChange }: {
  eq: EqualizerConfig
  onChange: (patch: Partial<EqualizerConfig>) => void
}) {
  return (
    <section className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3">
      <h2 className="text-sm font-semibold text-foreground">이퀄라이저 (오디오 반응 · pill · 로고 위)</h2>
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
          <input type="range" min={-500} max={500} step={1} value={eq.gap_above_logo}
            onChange={(e) => onChange({ gap_above_logo: Number(e.target.value) })}
            className="w-full accent-[var(--color-primary,#a78bfa)]" />
        </Field>
        <Field label={`가로 위치 (${Math.round((eq.x ?? 0.5) * 100)}%)`}>
          <input type="range" min={0} max={100} step={1} value={Math.round((eq.x ?? 0.5) * 100)}
            onChange={(e) => onChange({ x: Number(e.target.value) / 100 })}
            className="w-full accent-[var(--color-primary,#a78bfa)]" />
        </Field>
      </div>
    </section>
  )
}

function Field({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}
