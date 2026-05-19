"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { useRouter } from "next/navigation"
import {
  Check,
  ChevronRight,
  Sparkles,
  Wand2,
  Loader2,
  RefreshCw,
  ImageIcon,
  Save,
  Trash2,
  FolderOpen,
  Clapperboard,
} from "lucide-react"
import { toast } from "sonner"

// ── Outfit options (16) ───────────────────────────────────────────
const OUTFIT_OPTIONS = [
  { value: "trendy K-Street fashion, oversized denim jacket",             label: "트렌디 스트릿" },
  { value: "casual travel outfit, comfortable t-shirt and jeans",         label: "캐주얼 여행복" },
  { value: "luxury fashion, designer outfit, high-end clothing",          label: "럭셔리 스타일" },
  { value: "traditional Asian cultural outfit",                           label: "현지 전통의상" },
  { value: "resort beachwear, flowy sundress, beach hat",                 label: "럭셔리 비치" },
  { value: "minimalist chic, monochrome black and white outfit",          label: "시크 미니멀" },
  { value: "preppy style, cardigan with skirt, college look",             label: "프레피" },
  { value: "vintage 70s-80s retro fashion",                               label: "빈티지 레트로" },
  { value: "bohemian style, flowy maxi dress with prints",                label: "보헤미안" },
  { value: "sporty athletic wear, leggings and crop top",                 label: "스포츠 캐주얼" },
  { value: "feminine floral dress, soft pastel colors",                   label: "페미닌 원피스" },
  { value: "business casual, blouse with tailored pants",                 label: "비즈니스 캐주얼" },
  { value: "K-Pop idol stage outfit, trendy and bold",                    label: "K-Pop 아이돌" },
  { value: "evening night out outfit, elegant little black dress",        label: "야간 외출 룩" },
  { value: "cozy daily wear, oversized knit sweater",                     label: "데일리 코지" },
  { value: "modern casual, well-fitted contemporary outfit",              label: "모던 캐주얼" },
]

const HAIR_OPTIONS = [
  { value: "long wavy dark hair flowing past shoulders", label: "긴 웨이브" },
  { value: "long straight black hair",                   label: "긴 생머리" },
  { value: "medium-length layered hair",                 label: "미디엄 레이어드" },
  { value: "short bob haircut",                          label: "단발 보브" },
  { value: "high ponytail",                              label: "포니테일" },
  { value: "hair tied up in a bun",                      label: "묶음머리" },
]

const HEADWEAR_OPTIONS = [
  { value: "",                          label: "없음" },
  { value: "wearing a baseball cap",    label: "캡" },
  { value: "wearing a bucket hat",      label: "버킷햇" },
  { value: "wearing a fedora",          label: "페도라" },
  { value: "wearing a wide-brim hat",   label: "와이드햇" },
  { value: "wearing a beret",           label: "베레모" },
  { value: "wearing a beanie",          label: "비니" },
]

const EYEWEAR_OPTIONS = [
  { value: "",                              label: "없음" },
  { value: "wearing sunglasses",            label: "선글라스" },
  { value: "wearing glasses",               label: "일반 안경" },
  { value: "wearing colored sunglasses",    label: "컬러 선글라스" },
]

const BAG_OPTIONS = [
  { value: "",                          label: "없음" },
  { value: "carrying a crossbody bag",  label: "크로스백" },
  { value: "carrying a backpack",       label: "백팩" },
  { value: "carrying a tote bag",       label: "토트백" },
  { value: "carrying a mini bag",       label: "미니백" },
  { value: "carrying a clutch",         label: "클러치" },
  { value: "pulling a travel suitcase", label: "캐리어" },
]

const SHOES_OPTIONS = [
  { value: "wearing white sneakers",    label: "운동화" },
  { value: "wearing boots",             label: "부츠" },
  { value: "wearing sandals",           label: "샌들" },
  { value: "wearing flip-flops",        label: "슬리퍼" },
  { value: "wearing heels",             label: "힐" },
  { value: "wearing loafers",           label: "로퍼" },
]

const JEWELRY_OPTIONS = [
  { value: "wearing a watch",    label: "시계" },
  { value: "wearing a necklace", label: "목걸이" },
  { value: "wearing earrings",   label: "귀걸이" },
  { value: "wearing a bracelet", label: "팔찌" },
  { value: "wearing rings",      label: "반지" },
]

// ── Types ─────────────────────────────────────────────────────────
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

interface CharacterConfig {
  appearance: string
  outfit: string
  accessories: {
    headwear: string
    eyewear: string
    bag: string
    shoes: string
    jewelry: string[]
  }
  hair: string
}

interface CharacterImages {
  front: string
  side: string
  back: string
}

interface Character {
  id: string
  name: string
  createdAt: string
  config: CharacterConfig
  images: CharacterImages
}

// ── Helpers ───────────────────────────────────────────────────────
function SelectField({
  label,
  value,
  onChange,
  options,
  disabled,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
  disabled?: boolean
}) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-medium text-muted-foreground">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/30 disabled:opacity-50"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  )
}

function SkeletonCard() {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card animate-pulse">
      <div className="aspect-[3/4] bg-secondary/50" />
      <div className="p-3 space-y-2">
        <div className="h-3.5 w-2/3 rounded bg-secondary/60" />
        <div className="h-3 w-1/2 rounded bg-secondary/40" />
      </div>
    </div>
  )
}

function formatDate(iso: string) {
  return iso.slice(0, 10)
}

// ── Page ──────────────────────────────────────────────────────────
export default function CharacterPage() {
  const router = useRouter()
  const topRef = useRef<HTMLDivElement>(null)

  // Form state
  const [appearance,     setAppearance]     = useState("")
  const [selectedOutfit, setSelectedOutfit] = useState(OUTFIT_OPTIONS[1].value)
  const [hair,           setHair]           = useState(HAIR_OPTIONS[0].value)
  const [headwear,       setHeadwear]       = useState("")
  const [eyewear,        setEyewear]        = useState("")
  const [bag,            setBag]            = useState("")
  const [shoes,          setShoes]          = useState(SHOES_OPTIONS[0].value)
  const [jewelry,        setJewelry]        = useState<string[]>([])

  // Generation state
  const [step,      setStep]      = useState<GenerateStep>("idle")
  const [generated, setGenerated] = useState<CharacterImages | null>(null)
  const [errorMsg,  setErrorMsg]  = useState("")

  // Save state
  const [charName,  setCharName]  = useState("")
  const [saving,    setSaving]    = useState(false)

  // Library state
  const [library,      setLibrary]      = useState<Character[]>([])
  const [libLoading,   setLibLoading]   = useState(true)

  const isGenerating = step !== "idle" && step !== "done" && step !== "error"

  const fetchLibrary = useCallback(async () => {
    setLibLoading(true)
    try {
      const res = await fetch("/api/character/library")
      const data = await res.json()
      setLibrary(data.characters ?? [])
    } catch {
      // silently ignore
    } finally {
      setLibLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchLibrary()
  }, [fetchLibrary])

  function toggleJewelry(value: string) {
    setJewelry((prev) =>
      prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value]
    )
  }

  function buildConfig(): CharacterConfig {
    return {
      appearance,
      outfit: selectedOutfit,
      accessories: { headwear, eyewear, bag, shoes, jewelry },
      hair,
    }
  }

  function restoreConfig(config: CharacterConfig) {
    setAppearance(config.appearance ?? "")
    setSelectedOutfit(config.outfit ?? OUTFIT_OPTIONS[1].value)
    setHair(config.hair ?? HAIR_OPTIONS[0].value)
    setHeadwear(config.accessories?.headwear ?? "")
    setEyewear(config.accessories?.eyewear ?? "")
    setBag(config.accessories?.bag ?? "")
    setShoes(config.accessories?.shoes ?? SHOES_OPTIONS[0].value)
    setJewelry(config.accessories?.jewelry ?? [])
  }

  async function handleGenerate() {
    setStep("front")
    setGenerated(null)
    setErrorMsg("")
    setCharName("")

    try {
      const t1 = setTimeout(() => setStep("side"),   8000)
      const t2 = setTimeout(() => setStep("back"),   16000)
      const t3 = setTimeout(() => setStep("saving"), 24000)

      const res = await fetch("/api/character/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          appearance,
          outfit: selectedOutfit,
          hair,
          accessories: { headwear, eyewear, bag, shoes, jewelry },
        }),
      })

      clearTimeout(t1)
      clearTimeout(t2)
      clearTimeout(t3)

      const data = await res.json()
      if (!res.ok || !data.success) throw new Error(data.error ?? "API error")

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
    setCharName("")
  }

  async function handleSave() {
    if (!generated || !charName.trim()) return
    setSaving(true)
    try {
      const res = await fetch("/api/character/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: charName.trim(), config: buildConfig(), images: generated }),
      })
      const data = await res.json()
      if (!res.ok || !data.success) throw new Error(data.error ?? "저장 실패")
      toast.success("캐릭터가 저장되었어요")
      setCharName("")
      fetchLibrary()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "저장 중 오류가 발생했어요")
    } finally {
      setSaving(false)
    }
  }

  function handleLoad(char: Character) {
    restoreConfig(char.config)
    setGenerated(char.images)
    setStep("done")
    setCharName("")
    toast.success(`${char.name} 캐릭터를 불러왔어요`)
    topRef.current?.scrollIntoView({ behavior: "smooth" })
  }

  function handleVideoNav(char: Character) {
    sessionStorage.setItem("reelbot:selectedCharacter", JSON.stringify(char))
    router.push("/video")
  }

  async function handleDelete(char: Character) {
    if (!confirm(`"${char.name}" 캐릭터를 정말 삭제할까요? 되돌릴 수 없어요.`)) return
    try {
      const res = await fetch(`/api/character/${char.id}`, { method: "DELETE" })
      const data = await res.json()
      if (!res.ok || !data.success) throw new Error(data.error ?? "삭제 실패")
      toast.success(`${char.name} 캐릭터를 삭제했어요`)
      fetchLibrary()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "삭제 중 오류가 발생했어요")
    }
  }

  return (
    <div ref={topRef} className="flex flex-1 flex-col gap-6 overflow-auto p-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-foreground">캐릭터 설정</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">AI로 캐릭터를 생성하고 라이브러리에 저장하세요</p>
      </div>

      {/* ── Generation form ───────────────────────────────────────── */}
      <div className="rounded-xl border border-primary/20 bg-primary/5 p-5">
        <div className="mb-4 flex items-center gap-2">
          <Wand2 className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold text-foreground">직접 생성하기</h2>
          <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-medium text-primary">
            AI 생성
          </span>
        </div>

        <div className="flex flex-col gap-5">
          {/* Appearance */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
              외모 설명
            </label>
            <textarea
              rows={2}
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

          {/* Outfit 4×4 card grid */}
          <div>
            <label className="mb-2 block text-xs font-medium text-muted-foreground">
              의상 스타일
            </label>
            <div className="grid grid-cols-4 gap-2">
              {OUTFIT_OPTIONS.map((o) => {
                const active = selectedOutfit === o.value
                return (
                  <button
                    key={o.value}
                    onClick={() => setSelectedOutfit(o.value)}
                    disabled={isGenerating}
                    className={`relative flex items-center justify-center rounded-lg border px-2 py-2.5 text-center text-xs font-medium transition-all disabled:opacity-50 ${
                      active
                        ? "border-primary/60 bg-primary/15 text-foreground ring-1 ring-primary/30"
                        : "border-border bg-background text-muted-foreground hover:border-primary/30 hover:bg-primary/5 hover:text-foreground"
                    }`}
                  >
                    {active && (
                      <span className="absolute right-1.5 top-1.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-primary">
                        <Check className="h-2.5 w-2.5 text-primary-foreground" />
                      </span>
                    )}
                    {o.label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Hair */}
          <SelectField
            label="헤어 스타일"
            value={hair}
            onChange={setHair}
            options={HAIR_OPTIONS}
            disabled={isGenerating}
          />

          {/* Accessories */}
          <div>
            <p className="mb-2 text-xs font-medium text-muted-foreground">악세사리</p>
            <div className="grid grid-cols-2 gap-3">
              <SelectField
                label="모자/머리 장식"
                value={headwear}
                onChange={setHeadwear}
                options={HEADWEAR_OPTIONS}
                disabled={isGenerating}
              />
              <SelectField
                label="아이웨어"
                value={eyewear}
                onChange={setEyewear}
                options={EYEWEAR_OPTIONS}
                disabled={isGenerating}
              />
              <SelectField
                label="가방"
                value={bag}
                onChange={setBag}
                options={BAG_OPTIONS}
                disabled={isGenerating}
              />
              <SelectField
                label="신발"
                value={shoes}
                onChange={setShoes}
                options={SHOES_OPTIONS}
                disabled={isGenerating}
              />
            </div>

            {/* Jewelry multi-toggle */}
            <div className="mt-3">
              <label className="mb-2 block text-xs font-medium text-muted-foreground">
                주얼리 (복수 선택 가능)
              </label>
              <div className="flex flex-wrap gap-2">
                {JEWELRY_OPTIONS.map((j) => {
                  const active = jewelry.includes(j.value)
                  return (
                    <button
                      key={j.value}
                      onClick={() => toggleJewelry(j.value)}
                      disabled={isGenerating}
                      className={`rounded-full border px-3 py-1 text-xs font-medium transition-all disabled:opacity-50 ${
                        active
                          ? "border-primary/60 bg-primary/15 text-foreground"
                          : "border-border bg-background text-muted-foreground hover:border-primary/30 hover:text-foreground"
                      }`}
                    >
                      {active && "✓ "}{j.label}
                    </button>
                  )
                })}
              </div>
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
              <span className="text-xs text-muted-foreground">{STEP_LABELS[step]}</span>
            )}
            {step === "error" && (
              <span className="text-xs text-red-400">{errorMsg}</span>
            )}
          </div>
        </div>

        {/* Generated result */}
        {generated && (
          <div className="mt-5">
            <p className="mb-3 text-xs font-medium text-muted-foreground">생성된 캐릭터</p>

            {/* 3-image grid */}
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
                    className="aspect-[2/3] w-full object-contain bg-secondary/20"
                    onError={(e) => {
                      const el = e.currentTarget
                      el.style.display = "none"
                      el.nextElementSibling?.removeAttribute("hidden")
                    }}
                  />
                  <div hidden className="flex aspect-[2/3] items-center justify-center bg-secondary/40">
                    <ImageIcon className="h-8 w-8 text-muted-foreground/30" />
                  </div>
                  <p className="py-2 text-center text-xs font-medium text-muted-foreground">
                    {label}
                  </p>
                </div>
              ))}
            </div>

            {/* Action row */}
            <div className="mt-4 flex flex-wrap items-center gap-2">
              {/* Name input */}
              <input
                type="text"
                value={charName}
                onChange={(e) => setCharName(e.target.value)}
                maxLength={20}
                placeholder="예: 지수"
                className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/40 focus:border-primary/60 focus:outline-none focus:ring-1 focus:ring-primary/30 w-36"
              />

              {/* Save button */}
              <button
                onClick={handleSave}
                disabled={!charName.trim() || saving}
                className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-opacity hover:opacity-90 disabled:opacity-40"
              >
                {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
                저장
              </button>

              {/* Reset */}
              <button
                onClick={handleReset}
                className="flex items-center gap-1.5 rounded-lg border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-secondary/40"
              >
                <RefreshCw className="h-3.5 w-3.5 text-muted-foreground" />
                다시 생성
              </button>

              {/* Video nav */}
              <button
                onClick={() => {
                  const char: Character = {
                    id: "",
                    name: charName || "임시",
                    createdAt: new Date().toISOString(),
                    config: buildConfig(),
                    images: generated,
                  }
                  handleVideoNav(char)
                }}
                className="ml-auto flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90"
              >
                이 캐릭터로 영상 만들기
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── My Character Library ──────────────────────────────────── */}
      <div>
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-sm font-semibold text-foreground">내 캐릭터 라이브러리</h2>
          {!libLoading && (
            <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
              {library.length}개
            </span>
          )}
        </div>

        {libLoading ? (
          <div className="grid grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => <SkeletonCard key={i} />)}
          </div>
        ) : library.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card/40 py-12 text-center">
            <p className="text-sm font-medium text-muted-foreground">아직 저장된 캐릭터가 없어요</p>
            <p className="mt-1 text-xs text-muted-foreground/60">위에서 첫 캐릭터를 만들어보세요</p>
          </div>
        ) : (
          <div className="grid grid-cols-4 gap-4">
            {library.map((char) => (
              <div
                key={char.id}
                className="group relative overflow-hidden rounded-xl border border-border bg-card"
              >
                {/* Thumbnail */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={char.images.front}
                  alt={char.name}
                  className="aspect-[3/4] w-full object-cover bg-secondary/20"
                  onError={(e) => {
                    const el = e.currentTarget
                    el.style.display = "none"
                    el.nextElementSibling?.removeAttribute("hidden")
                  }}
                />
                <div hidden className="flex aspect-[3/4] w-full items-center justify-center bg-secondary/40">
                  <ImageIcon className="h-8 w-8 text-muted-foreground/30" />
                </div>

                {/* Info */}
                <div className="p-3">
                  <p className="truncate text-sm font-medium text-foreground">{char.name}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{formatDate(char.createdAt)}</p>
                </div>

                {/* Hover overlay */}
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-xl bg-black/80 opacity-0 backdrop-blur-sm transition-opacity duration-200 group-hover:pointer-events-auto group-hover:opacity-100">
                  <button
                    onClick={() => handleLoad(char)}
                    className="flex w-36 items-center justify-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground transition-opacity hover:opacity-90"
                  >
                    <FolderOpen className="h-3.5 w-3.5" />
                    불러오기
                  </button>
                  <button
                    onClick={() => handleVideoNav(char)}
                    className="flex w-36 items-center justify-center gap-1.5 rounded-lg bg-secondary px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-secondary/80"
                  >
                    <Clapperboard className="h-3.5 w-3.5" />
                    영상 만들기
                  </button>
                  <button
                    onClick={() => handleDelete(char)}
                    className="flex w-36 items-center justify-center gap-1.5 rounded-lg border border-red-500/30 px-3 py-2 text-xs font-medium text-red-400 transition-colors hover:bg-red-500/15"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    삭제
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
