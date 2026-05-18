"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { User, Plus, Check, ChevronRight, Sparkles } from "lucide-react"

const CHARACTERS = [
  {
    id: "jisoo",
    name: "지수",
    tags: ["청순", "트렌디"],
    tagColor: "text-violet-400 bg-violet-500/10",
  },
  {
    id: "haeun",
    name: "하은",
    tags: ["글래머", "시크"],
    tagColor: "text-cyan-400 bg-cyan-500/10",
  },
  {
    id: "junhyuk",
    name: "준혁",
    tags: ["캐주얼", "밝음"],
    tagColor: "text-amber-400 bg-amber-500/10",
  },
]

const OUTFIT_STYLES = [
  { id: "trendy", label: "트렌디 스트릿" },
  { id: "casual", label: "캐주얼 여행복" },
  { id: "luxury", label: "럭셔리 스타일" },
  { id: "traditional", label: "현지 전통의상" },
]

const ACCESSORIES = [
  { id: "sunglasses", label: "선글라스", defaultOn: true },
  { id: "crossbag", label: "크로스백", defaultOn: true },
  { id: "hat", label: "모자", defaultOn: false },
  { id: "jewelry", label: "주얼리", defaultOn: true },
]

function CharacterPlaceholder({ size = "lg" }: { size?: "lg" | "sm" }) {
  const cls =
    size === "lg"
      ? "h-full w-full flex items-center justify-center bg-secondary/60"
      : "h-full w-full flex items-center justify-center bg-secondary/40"
  return (
    <div className={cls}>
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

export default function CharacterPage() {
  const router = useRouter()
  const [selectedChar, setSelectedChar] = useState("jisoo")
  const [selectedOutfit, setSelectedOutfit] = useState("trendy")
  const [accessories, setAccessories] = useState<Record<string, boolean>>(
    Object.fromEntries(ACCESSORIES.map((a) => [a.id, a.defaultOn]))
  )

  const toggleAccessory = (id: string) =>
    setAccessories((prev) => ({ ...prev, [id]: !prev[id] }))

  return (
    <div className="flex flex-1 flex-col gap-6 p-6 overflow-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">캐릭터 설정</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            AI 캐릭터를 선택하거나 새로 생성하세요
          </p>
        </div>
        <button className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90">
          <Plus className="h-4 w-4" />
          새 캐릭터 만들기
        </button>
      </div>

      {/* Character Grid */}
      <div className="grid grid-cols-4 gap-4">
        {CHARACTERS.map((char) => {
          const isSelected = selectedChar === char.id
          return (
            <button
              key={char.id}
              onClick={() => setSelectedChar(char.id)}
              className={`relative rounded-xl border bg-card text-left transition-all overflow-hidden ${
                isSelected
                  ? "border-primary ring-1 ring-primary/30"
                  : "border-border hover:border-primary/40"
              }`}
            >
              {/* Selected badge */}
              {isSelected && (
                <div className="absolute right-2 top-2 z-10 flex h-5 w-5 items-center justify-center rounded-full bg-primary">
                  <Check className="h-3 w-3 text-primary-foreground" />
                </div>
              )}

              {/* Main image */}
              <div className="aspect-[3/4] overflow-hidden rounded-t-xl">
                <CharacterPlaceholder size="lg" />
              </div>

              {/* Thumbnails row */}
              <div className="flex gap-1 px-2 pt-2">
                {["측면", "뒷면"].map((label) => (
                  <div
                    key={label}
                    className="h-10 flex-1 overflow-hidden rounded-md"
                  >
                    <CharacterPlaceholder size="sm" />
                  </div>
                ))}
              </div>

              {/* Info */}
              <div className="p-3">
                <p className="text-sm font-semibold text-foreground">{char.name}</p>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {char.tags.map((tag) => (
                    <span
                      key={tag}
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${char.tagColor}`}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </button>
          )
        })}

        {/* New character card */}
        <button className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-card/50 p-6 text-muted-foreground transition-all hover:border-primary/40 hover:text-foreground min-h-[240px]">
          <div className="flex h-10 w-10 items-center justify-center rounded-full border border-dashed border-current">
            <Plus className="h-5 w-5" />
          </div>
          <p className="text-sm font-medium">새 생성</p>
        </button>
      </div>

      {/* Outfit & Accessories */}
      <div className="grid grid-cols-2 gap-4">
        {/* Outfit Styles */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h2 className="mb-4 text-sm font-semibold text-foreground">의상 스타일</h2>
          <div className="flex flex-col gap-2">
            {OUTFIT_STYLES.map((style) => {
              const isActive = selectedOutfit === style.id
              return (
                <button
                  key={style.id}
                  onClick={() => setSelectedOutfit(style.id)}
                  className={`flex items-center justify-between rounded-lg px-3 py-2.5 text-sm transition-all ${
                    isActive
                      ? "bg-primary/15 text-foreground border border-primary/30"
                      : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground border border-transparent"
                  }`}
                >
                  <span className="font-medium">{style.label}</span>
                  {isActive && <Check className="h-4 w-4 text-primary" />}
                </button>
              )
            })}
          </div>
        </div>

        {/* Accessories */}
        <div className="rounded-xl border border-border bg-card p-5">
          <h2 className="mb-4 text-sm font-semibold text-foreground">악세사리</h2>
          <div className="flex flex-col gap-3">
            {ACCESSORIES.map((acc) => {
              const isOn = accessories[acc.id]
              return (
                <div
                  key={acc.id}
                  className="flex items-center justify-between"
                >
                  <span className="text-sm text-foreground">{acc.label}</span>
                  <button
                    onClick={() => toggleAccessory(acc.id)}
                    className={`relative h-5 w-9 rounded-full transition-colors ${
                      isOn ? "bg-primary" : "bg-secondary"
                    }`}
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
