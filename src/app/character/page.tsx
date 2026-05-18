"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import {
  User,
  Plus,
  Check,
  ChevronRight,
  Sparkles,
  Wand2,
  Loader2,
  RefreshCw,
  ImageIcon,
} from "lucide-react"

// ── Mock preset characters ────────────────────────────────────────
const CHARACTERS = [
  { id: "jisoo",  name: "지수",  tags: ["청순", "트렌디"],    tagColor: "text-violet-400 bg-violet-500/10" },
  { id: "haeun",  name: "하은",  tags: ["글래머", "시크"],    tagColor: "text-cyan-400 bg-cyan-500/10"   },
  { id: "junhyuk",name: "준혁",  tags: ["캐주얼", "밝음"],    tagColor: "text-amber-400 bg-amber-500/10" },
]

const OUTFIT_OPTIONS = [
  { value: "trendy street fashion with crop top and wide-leg pants", label: "트렌디 스트릿" },
  { value: "casual travel outfit with jeans and comfortable sneakers", label: "캐주얼 여행복" },
  { value: "luxury fashion with elegant dress and heels", label: "럭셔리 스타일" },
  { value: "Korean traditional hanbok dress", label: "한복" },
  { value: "sporty athleisure outfit", label: "스포티 애슬레저" },
  { value: "minimalist chic outfit in neutral tones", label: "미니멀 시크" },
]

const HAIR_OPTIONS = [
  { value: "long wavy dark hair flowing past shoulders", label: "긴 웨이브" },
  { value: "short bob haircut", label: "단발" },
  { value: "high ponytail",     label: "포니테일" },
  { value: "two-strand braid",  label: "땋은 머리" },
  { value: "long straight black hair", label: "긴 생머리" },
]

const OUTFIT_STYLES_LEGACY = [
  { id: "trendy",      label: "트렌디 스트릿" },
  { id: "casual",      label: "캐주얼 여행복" },
  { id: "luxury",      label: "럭셔리 스타일" },
  { id: "traditional", label: "현지 전통의상" },
]

const ACCESSORIES = [
  { id: "sunglasses", label: "선글라스", defaultOn: true  },
  { id: "crossbag",   label: "크로스백",  defaultOn: true  },
  { id: "hat",        label: "모자",      defaultOn: false },
  { id: "jewelry",    label: "주얼리",    defaultOn: true  },
]

type GenerateStep = "idle" | "front" | "side" | "back" | "saving" | "done" | "error"

const STEP_LABELS: Record<GenerateStep, string> = {
  idle:   "",
  front:  "1/3 정면 이미지 생성 중...",
  side:   "2/3 측면 이미지 생성 중...",
  back:   "3/3 뒷모습 이미지 생성 중...",
  saving: "이미지 저장 중...",
  done:   "생성 완료!",
  error:  "생성 실패",
}

// ── Sub-components ────────────────────────────────────────────────
function CharacterPlaceholder({ size = "lg" }: { size?: "lg" | "sm" }) {
  return (
    <div
      className={`flex h-full w-full items-center justify-center ${
        size === "lg" ? "bg-secondary/60" : "bg-secondary/40"
      }`}
    >
      <User
        className={
          size === "lg"
            ? "h-10 w-10 text-muted-foreground/40"
            : "h-4 w-4 text-muted-foreground/40"
        }
      />
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────
export default function CharacterPage() {
  const router = useRouter()

  // Preset selection state
  const [selectedChar,   setSelectedChar]   = useState("jisoo")
  const [selectedOutfit, setSelectedOutfit] = useState("trendy")
  const [accessories,    setAccessories]    = useState<Record<string, boolean>>(
    Object.fromEntries(ACCESSORIES.map((a) => [a.id, a.defaultOn]))
  )

  // Generation form state
  const [appearance, setAppearance] = useState("")
  const [outfit,     setOutfit]     = useState(OUTFIT_OPTIONS[0].value)
  const [hair,       setHair]       = useState(HAIR_OPTIONS[0].value)
  const [step,       setStep]       = useState<GenerateStep>("idle")
  const [generated,  setGenerated]  = useState<{ front: string; side: string; back: string } | null>(null)
  const [errorMsg,   setErrorMsg]   = useState("")

  const isGenerating = step !== "idle" && step !== "done" && step !== "error"

  async function handleGenerate() {
    setStep("front")
    setGenerated(null)
    setErrorMsg("")

    try {
      // Simulate step progression while the single API call runs
      const stepTimer = setTimeout(() => setStep("side"), 8000)
      const stepTimer2 = setTimeout(() => setStep("back"), 16000)
      const stepTimer3 = setTimeout(() => setStep("saving"), 24000)

      const res = await fetch("/api/character/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ appearance, outfit, hair }),
      })

      clearTimeout(stepTimer)
      clearTimeout(stepTimer2)
      clearTimeout(stepTimer3)

      const data = await res.json()

      if (!res.ok || !data.success) {
        throw new Error(data.error ?? "API error")
      }

      setGenerated(data.images)
      setStep("done")
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "알 수 없는 오류")
      setStep("error")
    }
  }

  function handleReset() {
    setStep("idle")
    setGenerated(null)
    setErrorMsg("")
  }

  return (
    <div className="flex flex-1 flex-col gap-6 overflow-auto p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">캐릭터 설정</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            AI 캐릭터를 선택하거나 새로 생성하세요
          </p>
        </div>
      </div>

      {/* ── 직접 생성하기 ─────────────────────────────────────────── */}
      <div className="rounded-xl border border-primary/20 bg-primary/5 p-5">
        <div className="mb-4 flex items-center gap-2">
          <Wand2 className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold text-foreground">직접 생성하기</h2>
          <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-medium text-primary">
            AI 생성
          </span>
        </div>

        <div className="flex flex-col gap-3">
          {/* Appearance textarea */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
              외모 설명
            </label>
            <textarea
              rows={3}
              value={appearance}
              onChange={(e) => setAppearance(e.target.value)}
              disabled={isGenerating}
              placeholder={
                "예: slim build, fair skin, bright almond eyes, natural makeup\n" +
                "비워두면 기본값이 사용됩니다"
              }
              className="w-full resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/40 focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/30 disabled:opacity-50"
            />
          </div>

          {/* Outfit + Hair selects */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                의상 스타일
              </label>
              <select
                value={outfit}
                onChange={(e) => setOutfit(e.target.value)}
                disabled={isGenerating}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/30 disabled:opacity-50"
              >
                {OUTFIT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                헤어 스타일
              </label>
              <select
                value={hair}
                onChange={(e) => setHair(e.target.value)}
                disabled={isGenerating}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/30 disabled:opacity-50"
              >
                {HAIR_OPTIONS.map((h) => (
                  <option key={h.value} value={h.value}>{h.label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Generate button + status */}
          <div className="flex items-center gap-3">
            {step !== "done" ? (
              <button
                onClick={handleGenerate}
                disabled={isGenerating}
                className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-md shadow-primary/20 transition-opacity hover:opacity-90 disabled:opacity-60"
              >
                {isGenerating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                {isGenerating ? "생성 중..." : "✦ 캐릭터 생성"}
              </button>
            ) : (
              <button
                onClick={handleReset}
                className="flex items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-secondary/40"
              >
                <RefreshCw className="h-4 w-4 text-muted-foreground" />
                다시 생성
              </button>
            )}

            {isGenerating && (
              <span className="text-xs text-muted-foreground">
                {STEP_LABELS[step]}
              </span>
            )}
            {step === "error" && (
              <span className="text-xs text-red-400">{errorMsg}</span>
            )}
          </div>
        </div>

        {/* Generated result */}
        {generated && (
          <div className="mt-5">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-xs font-medium text-muted-foreground">생성된 캐릭터</p>
              <button
                onClick={() => router.push("/video")}
                className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground transition-opacity hover:opacity-90"
              >
                이 캐릭터로 영상 만들기
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="grid grid-cols-3 gap-3">
              {([
                { key: "front", label: "정면" },
                { key: "side",  label: "측면" },
                { key: "back",  label: "뒷모습" },
              ] as const).map(({ key, label }) => (
                <div key={key} className="overflow-hidden rounded-xl border border-border bg-card">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={generated[key]}
                    alt={label}
                    className="aspect-[3/4] w-full object-cover"
                    onError={(e) => {
                      const el = e.currentTarget
                      el.style.display = "none"
                      el.nextElementSibling?.removeAttribute("hidden")
                    }}
                  />
                  <div hidden className="flex aspect-[3/4] items-center justify-center bg-secondary/40">
                    <ImageIcon className="h-8 w-8 text-muted-foreground/30" />
                  </div>
                  <p className="py-2 text-center text-xs font-medium text-muted-foreground">
                    {label}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ── Preset characters ─────────────────────────────────────── */}
      <div>
        <h2 className="mb-3 text-sm font-semibold text-foreground">프리셋 캐릭터</h2>
        <div className="grid grid-cols-4 gap-4">
          {CHARACTERS.map((char) => {
            const isSelected = selectedChar === char.id
            return (
              <button
                key={char.id}
                onClick={() => setSelectedChar(char.id)}
                className={`relative overflow-hidden rounded-xl border bg-card text-left transition-all ${
                  isSelected
                    ? "border-primary ring-1 ring-primary/30"
                    : "border-border hover:border-primary/40"
                }`}
              >
                {isSelected && (
                  <div className="absolute right-2 top-2 z-10 flex h-5 w-5 items-center justify-center rounded-full bg-primary">
                    <Check className="h-3 w-3 text-primary-foreground" />
                  </div>
                )}
                <div className="aspect-[3/4] overflow-hidden rounded-t-xl">
                  <CharacterPlaceholder size="lg" />
                </div>
                <div className="flex gap-1 px-2 pt-2">
                  {["측면", "뒷면"].map((label) => (
                    <div key={label} className="h-10 flex-1 overflow-hidden rounded-md">
                      <CharacterPlaceholder size="sm" />
                    </div>
                  ))}
                </div>
                <div className="p-3">
                  <p className="text-sm font-semibold text-foreground">{char.name}</p>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {char.tags.map((tag) => (
                      <span key={tag} className={`rounded-full px-2 py-0.5 text-xs font-medium ${char.tagColor}`}>
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              </button>
            )
          })}

          {/* New slot */}
          <button className="flex min-h-[240px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-card/50 p-6 text-muted-foreground transition-all hover:border-primary/40 hover:text-foreground">
            <div className="flex h-10 w-10 items-center justify-center rounded-full border border-dashed border-current">
              <Plus className="h-5 w-5" />
            </div>
            <p className="text-sm font-medium">새 생성</p>
          </button>
        </div>
      </div>

      {/* ── Outfit & Accessories ──────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-xl border border-border bg-card p-5">
          <h2 className="mb-4 text-sm font-semibold text-foreground">의상 스타일</h2>
          <div className="flex flex-col gap-2">
            {OUTFIT_STYLES_LEGACY.map((style) => {
              const isActive = selectedOutfit === style.id
              return (
                <button
                  key={style.id}
                  onClick={() => setSelectedOutfit(style.id)}
                  className={`flex items-center justify-between rounded-lg border px-3 py-2.5 text-sm transition-all ${
                    isActive
                      ? "border-primary/30 bg-primary/15 text-foreground"
                      : "border-transparent text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
                  }`}
                >
                  <span className="font-medium">{style.label}</span>
                  {isActive && <Check className="h-4 w-4 text-primary" />}
                </button>
              )
            })}
          </div>
        </div>

        <div className="rounded-xl border border-border bg-card p-5">
          <h2 className="mb-4 text-sm font-semibold text-foreground">악세사리</h2>
          <div className="flex flex-col gap-3">
            {ACCESSORIES.map((acc) => {
              const isOn = accessories[acc.id]
              return (
                <div key={acc.id} className="flex items-center justify-between">
                  <span className="text-sm text-foreground">{acc.label}</span>
                  <button
                    onClick={() => setAccessories((p) => ({ ...p, [acc.id]: !p[acc.id] }))}
                    className={`relative h-5 w-9 rounded-full transition-colors ${isOn ? "bg-primary" : "bg-secondary"}`}
                  >
                    <span
                      className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                        isOn ? "translate-x-4" : "translate-x-0.5"
                      }`}
                    />
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* CTA */}
      <div className="flex justify-end">
        <button
          onClick={() => router.push("/video")}
          className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90"
        >
          <Sparkles className="h-4 w-4" />
          이 캐릭터로 영상 만들기
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
