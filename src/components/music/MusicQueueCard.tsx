"use client"

import { useCallback, useRef, useState } from "react"
import { toast } from "sonner"
import { Loader2, Music, Copy, Check, Upload, Globe, Trash2, MonitorPlay } from "lucide-react"
import { cn } from "@/lib/utils"

export interface VizSpec {
  primary_color?: string
  secondary_color?: string
  subtitle_en?: string
}
export interface QueueItem {
  slug: string
  mix_id: string
  title_kr?: string
  genre?: string
  mood?: string
  mp4_url?: string
  gpt_prompt?: string
  thumbnail_r2_key?: string | null
  thumbnail_url?: string | null
  viz_spec?: VizSpec | null
  status?: string
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

const cardClass = "flex flex-col overflow-hidden rounded-xl border border-border bg-card"

// 테스트 영상 카드(임시) — 그리드 첫 자리. DB·유튜브 미저장.
// variant: quick(빠른 10초, 보라 점선) / full(1곡 풀, 시안 점선 + 진행 단계).
export function TestCard({
  loading, video, variant = "quick", step,
}: {
  loading: boolean
  video: { url: string; engine?: string } | null
  variant?: "quick" | "full"
  step?: string
}) {
  const isFull = variant === "full"
  const borderCls = isFull ? "border-dashed border-cyan-500/40" : "border-dashed border-primary/40"
  const badgeCls = isFull ? "bg-cyan-500/20 text-cyan-300" : "bg-primary/20 text-primary"
  const badge = isFull ? "1곡 테스트 3~4분" : "테스트 10초"
  const title = isFull ? "1곡 풀 테스트" : "테스트 영상"
  return (
    <div className={cn(cardClass, borderCls)}>
      <div className="relative aspect-video w-full bg-black">
        {loading ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
            <Loader2 className="h-7 w-7 animate-spin" />
            {isFull && step && <span className="text-xs text-cyan-300">{step}…</span>}
          </div>
        ) : video ? (
          <video src={video.url} controls autoPlay className="h-full w-full" />
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground"><MonitorPlay className="h-7 w-7" /></div>
        )}
        <span className={cn("absolute left-2 top-2 rounded-full px-2 py-0.5 text-[11px] font-semibold", badgeCls)}>{badge}</span>
      </div>
      <div className="flex flex-col gap-1 p-3">
        <span className="text-sm font-semibold text-foreground">{title}</span>
        <span className="text-xs text-muted-foreground">
          {video?.engine ? `렌더 엔진: ${video.engine} · ` : ""}
          {isFull ? "진짜 음원 1곡 · " : ""}DB·유튜브에 저장되지 않습니다.
        </span>
      </div>
    </div>
  )
}

export function MusicQueueCard({ item, onChanged }: { item: QueueItem; onChanged: (keep?: string) => void }) {
  const [copied, setCopied] = useState(false)
  const [thumbUrl, setThumbUrl] = useState<string | null>(item.thumbnail_url ?? null)
  const [uploading, setUploading] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [published, setPublished] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const viz = item.viz_spec || undefined

  const copyPrompt = async () => {
    try {
      await navigator.clipboard.writeText(item.gpt_prompt || "")
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      toast.error("복사 실패 — 텍스트를 직접 선택해 복사하세요.")
    }
  }

  const handleFile = useCallback(
    async (file: File | undefined | null) => {
      if (!file) return
      if (!file.type.startsWith("image/")) { toast.error("이미지 파일만 업로드할 수 있습니다."); return }
      setUploading(true)
      try {
        const dataUrl = await fileToDataUrl(file)
        const res = await fetch(`/api/music/queue/${encodeURIComponent(item.mix_id)}/thumbnail`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ image_base64: dataUrl, slug: item.slug }),
        })
        const data = await res.json()
        if (!res.ok) throw new Error(data?.detail || "업로드 실패")
        setThumbUrl(`${data.thumbnail_url}?v=${Date.now()}`)
        toast.success("썸네일 업로드 완료")
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "썸네일 업로드 실패")
      } finally {
        setUploading(false)
      }
    },
    [item.mix_id, item.slug],
  )

  const publish = async () => {
    setPublishing(true)
    try {
      const res = await fetch(`/api/music/queue/${encodeURIComponent(item.mix_id)}/publish`, { method: "POST" })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || "업로드 실패")
      setPublished(data.youtube_url)
      toast.success("유튜브 공개 업로드 완료")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "공개 업로드 실패")
    } finally {
      setPublishing(false)
    }
  }

  const remove = async () => {
    if (!window.confirm("이 영상을 큐에서 삭제할까요? 되돌릴 수 없습니다.")) return
    setDeleting(true)
    try {
      const res = await fetch(`/api/music/queue/${encodeURIComponent(item.mix_id)}`, { method: "DELETE" })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || "삭제 실패")
      toast.success("큐에서 삭제했습니다.")
      onChanged("")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "삭제 실패")
      setDeleting(false)
    }
  }

  const hasThumb = Boolean(thumbUrl)

  return (
    <div className={cardClass}>
      {/* 영상 인라인(16:9, 컨트롤·풀스크린 기본) */}
      <div className="relative aspect-video w-full bg-black">
        {item.mp4_url ? (
          <video src={item.mp4_url} controls preload="metadata" className="h-full w-full" />
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground"><Music className="h-7 w-7" /></div>
        )}
        <span className={cn("absolute left-2 top-2 rounded-full px-2 py-0.5 text-[11px] font-medium", hasThumb ? "bg-emerald-500/20 text-emerald-300" : "bg-amber-500/20 text-amber-300")}>
          {hasThumb ? "썸네일 ✓" : "썸네일 없음"}
        </span>
      </div>

      <div className="flex flex-1 flex-col gap-3 p-3">
        {/* 정보 */}
        <div className="flex flex-col gap-1.5">
          <h3 className="truncate text-sm font-semibold text-foreground">{item.title_kr || item.slug}</h3>
          {viz?.subtitle_en && <p className="truncate text-xs italic text-muted-foreground">{viz.subtitle_en}</p>}
          <div className="flex flex-wrap items-center gap-1.5">
            {item.genre && <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[11px] text-primary">{item.genre}</span>}
            {item.mood && <span className="rounded-full bg-sky-500/15 px-2 py-0.5 text-[11px] text-sky-400">{item.mood}</span>}
            {viz?.primary_color && (
              <span className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: viz.primary_color }} />
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: viz.secondary_color || viz.primary_color }} />
                색감
              </span>
            )}
          </div>
        </div>

        {/* GPT 프롬프트 복사 */}
        <button
          type="button"
          onClick={copyPrompt}
          className="flex items-center justify-between gap-2 rounded-md border border-border bg-secondary/30 px-2.5 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
          title={item.gpt_prompt || ""}
        >
          <span className="truncate">GPT 프롬프트 복사</span>
          {copied ? <Check className="h-3.5 w-3.5 shrink-0 text-emerald-400" /> : <Copy className="h-3.5 w-3.5 shrink-0" />}
        </button>

        {/* 썸네일 업로드 */}
        <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => handleFile(e.target.files?.[0])} />
        <div
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); handleFile(e.dataTransfer.files?.[0]) }}
          className="flex min-h-[72px] cursor-pointer items-center justify-center overflow-hidden rounded-md border border-dashed border-border bg-secondary/20 text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
        >
          {uploading ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : thumbUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={thumbUrl} alt="썸네일 미리보기" className="max-h-32 w-full object-contain" />
          ) : (
            <span className="flex flex-col items-center gap-1 py-2 text-[11px]"><Upload className="h-4 w-4" /> 깨끗한 이미지 업로드</span>
          )}
        </div>

        {/* 공개 + 삭제 */}
        <div className="mt-auto flex items-center gap-2">
          {published ? (
            <a href={published} target="_blank" rel="noreferrer" className="inline-flex h-10 flex-1 items-center justify-center gap-1.5 rounded-md bg-emerald-500/15 text-xs font-medium text-emerald-400 hover:bg-emerald-500/25">
              <MonitorPlay className="h-4 w-4" /> 영상 보기
            </a>
          ) : (
            <button
              type="button"
              onClick={publish}
              disabled={!hasThumb || publishing}
              className={cn("inline-flex h-10 flex-1 items-center justify-center gap-1.5 rounded-md text-xs font-medium", hasThumb ? "bg-emerald-600 text-white hover:opacity-90" : "border border-border text-muted-foreground")}
              title={hasThumb ? "유튜브 공개 업로드" : "이미지를 먼저 업로드하세요"}
            >
              {publishing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Globe className="h-4 w-4" />} 공개 업로드
            </button>
          )}
          <button
            type="button"
            onClick={remove}
            disabled={deleting}
            className="inline-flex h-10 items-center justify-center rounded-md border border-red-500/30 px-2.5 text-red-400 hover:bg-red-500/15"
            title="큐에서 삭제"
          >
            {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </div>
  )
}
