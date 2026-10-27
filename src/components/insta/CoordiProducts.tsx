"use client"

import { useState } from "react"
import { toast } from "sonner"
import { EyeOff, ExternalLink, Loader2 } from "lucide-react"
import { jsonOrThrow } from "@/components/studio/studio-lib"

// 착장 결과의 상품 목록(A2-3a) — 상품마다 사진·이름·쇼핑몰·링크. 쿠팡이 고른 건 "다른 후보"(최대 3)로 교체,
// 교체하면 "바뀐 상품으로 다시 입히기". 상품 "내리기"(사유 기록 — 예: 판매자 요청). 링크는 새 창으로만 연다.

export interface CoordiProd {
  id: number | null; channel: "bose" | "coupang" | "naver"; name: string | null; price?: number | null
  mall: string | null; image: string | null; link: string | null; affiliate_link?: string | null
  hidden_at?: string | null; hidden_reason?: string | null
}
export interface CoordiItem { index: number; kind: string; source?: string; pick: CoordiProd | null; backups: CoordiProd[]; notes?: string[] }
export interface CoordiLook { id: string; concept: string | null; source?: string; items: CoordiItem[]; error?: string | null }

export const KIND_KO: Record<string, string> = { top: "상의", bottoms: "하의", dress: "원피스", outerwear: "아우터", shoes: "신발", bag: "가방", accessory: "액세서리" }
export const HIDE_REASONS = ["판매자 요청", "품절·판매 중지", "마음에 안 들어요", "기타"]

function won(n?: number | null) {
  return n ? `${n.toLocaleString("ko-KR")}원` : ""
}

/** 내리기 — 사유를 고르고 한 번 더 눌러야 실행(실수 방지). */
export function HideButton({ label, onHide, disabled }: { label: string; onHide: (reason: string) => Promise<void>; disabled?: boolean }) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState(HIDE_REASONS[0])
  const [busy, setBusy] = useState(false)
  if (!open) {
    return (
      <button onClick={() => setOpen(true)} disabled={disabled}
        className="flex min-h-[28px] items-center gap-1 rounded-md px-1.5 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50">
        <EyeOff className="h-3 w-3" /> {label}
      </button>
    )
  }
  return (
    <span className="flex min-w-0 flex-wrap items-center gap-1">
      <select value={reason} onChange={(e) => setReason(e.target.value)} aria-label="내리는 이유"
        className="min-w-0 rounded-md border border-border bg-background px-1 py-0.5 text-[11px] text-foreground">
        {HIDE_REASONS.map((r) => <option key={r} value={r}>{r}</option>)}
      </select>
      <button
        onClick={async () => {
          setBusy(true)
          try {
            await onHide(reason)
            setOpen(false)
          } finally {
            setBusy(false)
          }
        }}
        disabled={busy}
        className="rounded-md border border-red-500/40 px-1.5 py-0.5 text-[11px] text-red-400 hover:bg-red-500/10 disabled:opacity-50">
        {busy ? "내리는 중…" : "내리기"}
      </button>
      <button onClick={() => setOpen(false)} className="px-1 text-[11px] text-muted-foreground hover:text-foreground">취소</button>
    </span>
  )
}

export function CoordiProducts({ look, disabled, onChanged }: { look: CoordiLook; disabled?: boolean; onChanged: (swapped: boolean) => void }) {
  const [swapping, setSwapping] = useState<number | null>(null)

  async function swap(it: CoordiItem, p: CoordiProd) {
    if (p.id == null) return
    setSwapping(it.index)
    try {
      await jsonOrThrow(await fetch(`/api/insta/looks/${encodeURIComponent(look.id)}/swap`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ item_index: it.index, product_id: p.id }),
      }))
      onChanged(true)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "교체하지 못했어요")
    } finally {
      setSwapping(null)
    }
  }

  async function hide(p: CoordiProd, reason: string) {
    if (p.id == null) return
    try {
      await jsonOrThrow(await fetch(`/api/insta/products/${p.id}/hide`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason }),
      }))
      toast.success("상품을 내렸어요")
      onChanged(false)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "내리지 못했어요")
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <p className="text-[11px] font-medium text-foreground">입힌 상품</p>
      <div className="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-2">
        {look.items.map((it) => {
          const p = it.pick
          const hidden = !!p?.hidden_at
          const href = p ? p.affiliate_link || p.link : null
          return (
            <div key={it.index} className={`flex min-w-0 flex-col gap-1.5 rounded-lg border border-border bg-background p-2 ${hidden ? "opacity-50" : ""}`}>
              <div className="flex min-w-0 items-center gap-1.5 text-[11px]">
                <span className="font-medium text-muted-foreground">{KIND_KO[it.kind] ?? it.kind}</span>
                <span className={`rounded px-1 ${p?.channel === "bose" ? "bg-primary/15 text-primary" : "bg-secondary text-muted-foreground"}`}>
                  {p?.channel === "bose" ? "내 상품" : "AI가 고름"}
                </span>
                {hidden && <span className="text-red-400" title={p?.hidden_reason ?? ""}>내림</span>}
              </div>
              {p ? (
                <div className="flex min-w-0 gap-2">
                  <div className="h-16 w-16 shrink-0 overflow-hidden rounded-md bg-secondary/30">
                    {p.image && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={p.image} alt={p.name ?? ""} className="h-full w-full object-contain" />
                    )}
                  </div>
                  <div className="flex min-w-0 flex-col gap-0.5 text-xs">
                    <span className="line-clamp-2 text-foreground">{p.name || KIND_KO[it.kind]}</span>
                    <span className="truncate text-muted-foreground">{[p.mall, won(p.price)].filter(Boolean).join(" · ") || "쇼핑몰 정보 없음"}</span>
                    <span className="flex min-w-0 flex-wrap items-center gap-1">
                      {href && (
                        <a href={href} target="_blank" rel="noreferrer noopener" className="flex items-center gap-0.5 text-[11px] text-primary hover:underline">
                          <ExternalLink className="h-3 w-3" /> 상품 보기
                        </a>
                      )}
                      {p.id != null && !hidden && <HideButton label="상품 내리기" disabled={disabled} onHide={(r) => hide(p, r)} />}
                    </span>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-amber-400">{it.notes?.at(-1) ?? "맞는 상품을 못 찾았어요"}</p>
              )}
              {it.backups.length > 0 && (
                <div className="flex min-w-0 flex-col gap-1">
                  <p className="text-[11px] text-muted-foreground">다른 후보 — 누르면 바꿔요</p>
                  <div className="flex gap-1.5">
                    {it.backups.slice(0, 3).map((b) => (
                      <button key={`${b.channel}-${b.id}`} onClick={() => swap(it, b)} disabled={disabled || swapping !== null || b.id == null}
                        title={`${b.name ?? ""} ${won(b.price)}`}
                        className="relative h-12 w-12 shrink-0 overflow-hidden rounded-md border border-border bg-secondary/30 hover:border-primary/60 disabled:opacity-50">
                        {b.image && (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={b.image} alt="" className="h-full w-full object-contain" />
                        )}
                        {swapping === it.index && <span className="absolute inset-0 flex items-center justify-center bg-background/60"><Loader2 className="h-3.5 w-3.5 animate-spin" /></span>}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
