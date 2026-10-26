"use client"

import { useRef, useState } from "react"
import { toast } from "sonner"
import { CheckCircle2, ChevronDown, ExternalLink, ImageIcon, Loader2, RefreshCw, Trash2, Upload } from "lucide-react"
import { USD_PER_IMAGE, jsonOrThrow, uploadOne, usd, type GenItem, type Ref, type RoleSlot } from "./studio-lib"

// 역할 카드 — 확정 1장 + 후보(클릭 = 확정), 버리기·교체 업로드, "다시 생성"(후보 2장 추가),
// "고급 보기"(접힘: 프롬프트 확인·수정 후 재생성). 생성 가능 여부(canGenerate)는 부모가 정한다.

const REGEN_COUNT = 2

export function RoleCard({ characterId, slot, label, required, busyRef, canGenerate, genBlockedReason, generating, onAct, onOpen, onChanged, onGenerate }: {
  characterId: string
  slot: RoleSlot
  label: string
  required: boolean
  busyRef: number | null
  canGenerate: boolean
  genBlockedReason?: string
  generating: boolean
  onAct: (ref: Ref, action: "confirm" | "discard") => void
  /** 사진 클릭 = 크게 보기(확정 변경은 크게 보기 안 버튼으로만) */
  onOpen: (role: string, ref: Ref) => void
  onChanged: () => Promise<unknown>
  onGenerate: (items: GenItem[]) => Promise<boolean>
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [advanced, setAdvanced] = useState(false)
  const [prompt, setPrompt] = useState<string | null>(null)
  const [loadingPrompt, setLoadingPrompt] = useState(false)
  const c = slot.confirmed
  const cost = usd(REGEN_COUNT * USD_PER_IMAGE)

  async function replace(file: File) {
    setUploading(true)
    try {
      await uploadOne(characterId, file, slot.role, true)
      toast.success(`${slot.role} 교체 — 이전 확정은 후보로 남아요`)
      await onChanged()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "업로드 실패")
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ""
    }
  }

  async function openAdvanced() {
    const next = !advanced
    setAdvanced(next)
    if (!next || prompt !== null) return
    // 확정 → 후보 순으로 저장된 프롬프트, 없으면(업로드 이미지) 기본 프롬프트를 받아 온다.
    const saved = c?.prompt || slot.candidates.find((r) => r.prompt)?.prompt
    if (saved) {
      setPrompt(saved)
      return
    }
    setLoadingPrompt(true)
    try {
      const d = await jsonOrThrow(await fetch(`/api/studio/characters/${encodeURIComponent(characterId)}/plan?role=${encodeURIComponent(slot.role)}`, { cache: "no-store" }))
      setPrompt(d.prompt ?? "")
    } catch (e) {
      setPrompt("")
      toast.error(e instanceof Error ? e.message : "프롬프트를 불러오지 못했어요")
    } finally {
      setLoadingPrompt(false)
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-xl border border-border bg-card p-3">
      <div className="flex min-w-0 items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-foreground">
            {slot.role}
            {required && <span className="ml-1.5 text-[10px] font-medium text-primary">필수</span>}
          </p>
          <p className="truncate text-[11px] text-muted-foreground">
            {label}
            {c?.w && c?.h ? ` · ${c.w}×${c.h}` : ""}
            {c ? ` · ${c.source === "upload" ? "업로드" : "생성"}` : ""}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {c ? (
            <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-400"><CheckCircle2 className="h-3.5 w-3.5" /> 확정</span>
          ) : (
            <span className="text-[11px] text-amber-400">미확정</span>
          )}
          <button
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
            title={c ? "다른 이미지로 교체" : "이미지 올리기"}
            className="ml-1 flex min-h-[32px] items-center gap-1 rounded-lg border border-border bg-background px-2 text-xs font-medium text-foreground hover:border-primary/40 disabled:opacity-50"
          >
            {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
            {c ? "교체" : "업로드"}
          </button>
          <input
            ref={inputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) replace(f)
            }}
          />
        </div>
      </div>

      <div className="relative flex h-56 items-center justify-center overflow-hidden rounded-lg bg-secondary/30">
        {c ? (
          <button type="button" onClick={() => onOpen(slot.role, c)} title="크게 보기" className="h-full w-full">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={c.url} alt={slot.role} className="h-full w-full object-contain" />
          </button>
        ) : (
          <ImageIcon className="h-6 w-6 text-muted-foreground/30" />
        )}
        {c && (
          <button
            onClick={() => onAct(c, "discard")}
            disabled={busyRef !== null}
            aria-label="확정 이미지 버리기"
            title="버리기"
            className="absolute right-1.5 top-1.5 rounded-md border border-border bg-background/80 p-1 text-muted-foreground hover:text-red-400 disabled:opacity-50"
          >
            {busyRef === c.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
          </button>
        )}
      </div>

      {slot.candidates.length > 0 && (
        <div className="flex flex-col gap-1">
          <p className="text-[11px] text-muted-foreground">후보 {slot.candidates.length}장 — 눌러서 크게 보고 바꿀 수 있어요</p>
          <div className={`grid gap-1.5 ${slot.candidates.length >= 4 ? "grid-cols-4" : "grid-cols-3"}`}>
            {slot.candidates.map((r) => (
              <div key={r.id} className="group relative">
                <button
                  onClick={() => onOpen(slot.role, r)}
                  disabled={busyRef !== null}
                  title="크게 보기"
                  className="block h-24 w-full overflow-hidden rounded-md border border-border bg-secondary/30 hover:border-primary/60 disabled:opacity-60"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={r.url} alt={`${slot.role} 후보`} className="h-full w-full object-contain" />
                  {busyRef === r.id && (
                    <span className="absolute inset-0 flex items-center justify-center bg-background/60"><Loader2 className="h-4 w-4 animate-spin text-primary" /></span>
                  )}
                </button>
                <div className="absolute right-0.5 top-0.5 flex gap-0.5">
                  <a href={r.url} target="_blank" rel="noreferrer" aria-label="크게 보기" className="rounded bg-background/80 p-0.5 text-muted-foreground hover:text-foreground">
                    <ExternalLink className="h-3 w-3" />
                  </a>
                  <button onClick={() => onAct(r, "discard")} disabled={busyRef !== null} aria-label="후보 버리기" className="rounded bg-background/80 p-0.5 text-muted-foreground hover:text-red-400 disabled:opacity-50">
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => onGenerate([{ role: slot.role, count: REGEN_COUNT }])}
          disabled={!canGenerate || generating}
          title={canGenerate ? `같은 역할 후보 ${REGEN_COUNT}장 추가` : genBlockedReason}
          className="flex min-h-[32px] items-center gap-1 rounded-lg border border-border bg-background px-2 text-xs font-medium text-foreground hover:border-primary/40 disabled:opacity-50"
        >
          <RefreshCw className="h-3.5 w-3.5" /> 다시 생성 <span className="text-muted-foreground">{REGEN_COUNT}장 · {cost}</span>
        </button>
        <button onClick={openAdvanced} className="ml-auto flex items-center gap-0.5 text-[11px] text-muted-foreground hover:text-foreground">
          고급 보기 <ChevronDown className={`h-3 w-3 transition-transform ${advanced ? "rotate-180" : ""}`} />
        </button>
      </div>
      {!canGenerate && genBlockedReason && <p className="text-[11px] text-muted-foreground">{genBlockedReason}</p>}

      {advanced && (
        <div className="flex flex-col gap-1.5 rounded-lg border border-border bg-background p-2">
          {loadingPrompt ? (
            <span className="flex items-center gap-1 text-[11px] text-muted-foreground"><Loader2 className="h-3 w-3 animate-spin" /> 불러오는 중</span>
          ) : (
            <>
              <textarea
                value={prompt ?? ""}
                onChange={(e) => setPrompt(e.target.value)}
                rows={6}
                className="w-full min-w-0 resize-y rounded-md border border-border bg-background p-1.5 text-[11px] leading-relaxed text-foreground"
              />
              <p className="text-[11px] text-muted-foreground">
                체형 강조 표현·&quot;cropped at the neck&quot;은 안전 필터에 걸려요. 체형은 02_body 이미지가 담당해요.
              </p>
              <button
                onClick={() => prompt && onGenerate([{ role: slot.role, prompt, count: REGEN_COUNT }])}
                disabled={!canGenerate || generating || !prompt?.trim()}
                className="flex min-h-[32px] items-center justify-center gap-1 self-end rounded-lg bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                <RefreshCw className="h-3.5 w-3.5" /> 이 프롬프트로 {REGEN_COUNT}장 생성 · {cost}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
