"use client"

import { useRef, useState } from "react"
import { toast } from "sonner"
import { Check, CheckCircle2, ImageIcon, Loader2, Upload, X } from "lucide-react"

// 쇼츠 가족 캐스트(업로드 role) — 슬롯별 업로드·교체·미리보기, 시트 칸 수(4/5)·칸별 라벨·자르지 않기,
// role 단위 확정. 이미지는 대표가 외부(메타 AI)에서 만든 것. 영상 레퍼런스는 칸 라벨 기준으로 고른다.

export interface CastSlot {
  key: string
  label: string
  kind: "single" | "strip" | "grid"
  required: boolean
  min: "face" | "other"
  url: string | null
  w?: number | null
  h?: number | null
  cols?: number
  crop?: boolean
  labels?: string[]
  label_options?: string[]
  panels?: (string | null)[]
}
export interface UploadRole {
  role: string
  label: string
  summary: string
  active: boolean
  status: "draft" | "approved"
  missing: string[]
  slots: CastSlot[]
}

const LABEL_KO: Record<string, string> = {
  front: "정면", threequarter: "반측면", side: "측면", back: "뒤", expr: "사용", unused: "사용안함",
}
// Vercel 함수 본문 한도 4.5MB — 여유를 두고 3.8MB 를 넘으면 브라우저에서 줄여 보낸다.
const MAX_SEND = 3.8 * 1024 * 1024

async function jsonOrThrow(res: Response) {
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    if (res.status === 413) throw new Error("이미지가 너무 커요 — 4MB 이하로 줄여서 올려 주세요.")
    throw new Error(typeof data?.detail === "string" ? data.detail : `요청 실패(${res.status})`)
  }
  return data
}

/** 큰 파일은 긴 변 maxLong 으로 줄이고 JPEG 로 다시 압축(서버가 PNG 로 통일). */
async function prepareFile(file: File, maxLong: number): Promise<File> {
  if (!/\.(png|jpe?g|webp)$/i.test(file.name)) throw new Error("png·jpg·webp 이미지만 올릴 수 있어요.")
  if (file.size <= MAX_SEND) return file
  const bmp = await createImageBitmap(file)
  const scale = Math.min(1, maxLong / Math.max(bmp.width, bmp.height))
  const canvas = document.createElement("canvas")
  canvas.width = Math.round(bmp.width * scale)
  canvas.height = Math.round(bmp.height * scale)
  canvas.getContext("2d")?.drawImage(bmp, 0, 0, canvas.width, canvas.height)
  for (const q of [0.92, 0.85, 0.75]) {
    const blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, "image/jpeg", q))
    if (blob && blob.size <= MAX_SEND) return new File([blob], "upload.jpg", { type: "image/jpeg" })
  }
  throw new Error("이미지가 너무 커요 — 4MB 이하로 줄여서 올려 주세요.")
}

function SlotCard({ channel, role, slot, onChanged }: {
  channel: string; role: string; slot: CastSlot; onChanged: () => Promise<unknown>
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [cols, setCols] = useState(slot.cols ?? 4)
  const isSheet = slot.kind !== "single"

  async function upload(file: File) {
    setBusy(true)
    try {
      const prepared = await prepareFile(file, isSheet ? 3072 : 2048)
      const fd = new FormData()
      fd.append("file", prepared, prepared.name)
      fd.append("channel", channel)
      fd.append("role", role)
      fd.append("aspect", slot.key)
      if (slot.kind === "strip") fd.append("cols", String(cols))
      await jsonOrThrow(await fetch("/api/shorts/cast/upload", { method: "POST", body: fd }))
      toast.success(`${slot.label} 저장 — 확정은 다시 눌러 주세요`)
      await onChanged()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "업로드 실패")
    } finally {
      setBusy(false)
      if (inputRef.current) inputRef.current.value = ""
    }
  }

  async function patch(body: { cols?: number; crop?: boolean; labels?: string[] }) {
    setBusy(true)
    try {
      await jsonOrThrow(await fetch("/api/shorts/cast/slot", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel, role, aspect: slot.key, ...body }),
      }))
      await onChanged()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "저장 실패")
    } finally {
      setBusy(false)
    }
  }

  const minText = slot.min === "face" ? "짧은 변 768px 이상" : "긴 변 1024px 이상"
  const panelsOn = isSheet && slot.url && slot.crop !== false

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-foreground">
            {slot.label}
            {slot.required && <span className="ml-1.5 text-[10px] font-medium text-primary">필수</span>}
          </p>
          <p className="text-[11px] text-muted-foreground">
            {slot.w && slot.h ? `${slot.w}×${slot.h} · ` : ""}png·jpg·webp · {minText}
          </p>
        </div>
        <button
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          className="flex min-h-[36px] shrink-0 items-center gap-1.5 rounded-lg border border-border bg-background px-2.5 text-xs font-medium text-foreground hover:border-primary/40 disabled:opacity-50"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
          {slot.url ? "교체" : "업로드"}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) upload(f)
          }}
        />
      </div>

      <div className="relative flex h-48 items-center justify-center overflow-hidden rounded-lg bg-secondary/30">
        {slot.url ? (
          <a href={slot.url} target="_blank" rel="noreferrer" className="h-full w-full">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={slot.url} alt={slot.label} className="h-full w-full object-contain" />
          </a>
        ) : (
          <ImageIcon className="h-6 w-6 text-muted-foreground/30" />
        )}
        {busy && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/60">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
          </div>
        )}
      </div>

      {isSheet && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {slot.kind === "strip" ? (
            <label className="flex items-center gap-1.5">
              칸 수
              <select
                value={cols}
                disabled={busy}
                onChange={(e) => {
                  const n = Number(e.target.value)
                  setCols(n)
                  if (slot.url) patch({ cols: n })
                }}
                className="rounded-md border border-border bg-background px-1.5 py-1 text-xs text-foreground"
              >
                <option value={4}>4칸</option>
                <option value={5}>5칸</option>
              </select>
            </label>
          ) : (
            <span>2×2 표정 시트</span>
          )}
          {slot.url && (
            <label className="ml-auto flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={slot.crop === false}
                disabled={busy}
                onChange={(e) => patch({ crop: !e.target.checked })}
              />
              자르지 않기
            </label>
          )}
        </div>
      )}

      {panelsOn && slot.labels && (
        <div className={`grid gap-1.5 ${slot.labels.length === 5 ? "grid-cols-5" : "grid-cols-4"}`}>
          {slot.labels.map((lb, i) => (
            <div key={i} className="flex min-w-0 flex-col gap-1">
              <div className={`flex h-24 items-center justify-center overflow-hidden rounded-md bg-secondary/30 ${lb === "unused" ? "opacity-40" : ""}`}>
                {slot.panels?.[i] ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={slot.panels[i] as string} alt={`${i + 1}칸`} className="h-full w-full object-contain" />
                ) : (
                  <ImageIcon className="h-4 w-4 text-muted-foreground/30" />
                )}
              </div>
              <select
                value={lb}
                disabled={busy}
                onChange={(e) => {
                  const next = [...(slot.labels ?? [])]
                  next[i] = e.target.value
                  patch({ labels: next })
                }}
                className={`w-full min-w-0 rounded-md border border-border bg-background py-1 text-foreground ${slot.labels?.length === 5 ? "px-0 text-[10px]" : "px-1 text-[11px]"}`}
              >
                {(slot.label_options ?? []).map((o) => (
                  <option key={o} value={o}>{LABEL_KO[o] ?? o}</option>
                ))}
              </select>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function FamilyRolePanel({ channel, role, onChanged }: {
  channel: string; role: UploadRole; onChanged: () => Promise<unknown>
}) {
  const [approving, setApproving] = useState(false)

  async function approve(approved: boolean) {
    setApproving(true)
    try {
      await jsonOrThrow(await fetch("/api/shorts/cast/approve", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel, role: role.role, approved }),
      }))
      toast.success(approved ? `${role.label} 확정` : `${role.label} 확정 해제`)
      await onChanged()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "저장 실패")
    } finally {
      setApproving(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3 md:flex-row md:items-center md:justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-foreground">{role.label}</span>
          {role.status === "approved" ? (
            <span className="flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-400">
              <CheckCircle2 className="h-3 w-3" />
              확정
            </span>
          ) : (
            <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[11px] font-medium text-primary">검토 중</span>
          )}
          <span className="text-xs text-muted-foreground">{role.summary}</span>
          {role.missing.length > 0 && (
            <p className="w-full text-[11px] text-muted-foreground">필수 이미지 남음: {role.missing.join(", ")}</p>
          )}
        </div>
        {role.status === "approved" ? (
          <button
            onClick={() => approve(false)}
            disabled={approving}
            className="flex min-h-[40px] shrink-0 items-center gap-1.5 self-start rounded-lg border border-emerald-500/40 px-3 text-sm font-semibold text-emerald-400 hover:bg-emerald-500/10 disabled:opacity-40 md:self-auto"
          >
            <X className="h-4 w-4" />
            확정 해제
          </button>
        ) : (
          <button
            onClick={() => approve(true)}
            disabled={approving || role.missing.length > 0}
            title={role.missing.length ? "필수 이미지가 모두 있어야 확정할 수 있어요" : `${role.label} 확정`}
            className="flex min-h-[40px] shrink-0 items-center gap-1.5 self-start rounded-lg bg-emerald-600 px-3 text-sm font-semibold text-white shadow-sm hover:opacity-90 disabled:opacity-40 md:self-auto"
          >
            <Check className="h-4 w-4" />
            확정
          </button>
        )}
      </div>
      <div className="grid grid-cols-1 items-start gap-3 md:grid-cols-2 xl:grid-cols-3">
        {role.slots.map((s) => (
          <SlotCard key={`${s.key}-${s.cols ?? 0}`} channel={channel} role={role.role} slot={s} onChanged={onChanged} />
        ))}
      </div>
    </div>
  )
}
