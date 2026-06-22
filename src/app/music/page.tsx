"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { Copy, Check, Upload, Globe, MonitorPlay, Loader2, BookOpen, Music } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

interface QueueItem {
  slug: string
  mix_id: string
  title_kr?: string
  genre?: string
  mood?: string
  mp4_url?: string
  gpt_prompt?: string
  thumbnail_r2_key?: string | null
  thumbnail_url?: string | null
  created_at?: string
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

function QueueCard({ item, onChanged }: { item: QueueItem; onChanged: () => void }) {
  const [copied, setCopied] = useState(false)
  const [thumbUrl, setThumbUrl] = useState<string | null>(item.thumbnail_url ?? null)
  const [uploading, setUploading] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [published, setPublished] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

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
      if (!file.type.startsWith("image/")) {
        toast.error("이미지 파일만 업로드할 수 있습니다.")
        return
      }
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
        // 캐시 버스팅으로 미리보기 갱신.
        setThumbUrl(`${data.thumbnail_url}?v=${Date.now()}`)
        toast.success("썸네일 업로드 완료")
        onChanged()
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "썸네일 업로드 실패")
      } finally {
        setUploading(false)
      }
    },
    [item.mix_id, item.slug, onChanged],
  )

  const publish = async () => {
    setPublishing(true)
    try {
      const res = await fetch(`/api/music/queue/${encodeURIComponent(item.mix_id)}/publish`, {
        method: "POST",
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || "업로드 실패")
      setPublished(data.youtube_url)
      toast.success("유튜브 공개 업로드 완료")
      onChanged()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "공개 업로드 실패")
    } finally {
      setPublishing(false)
    }
  }

  const hasThumb = Boolean(thumbUrl)

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-border bg-card p-4 md:flex-row">
      {/* 영상 플레이어(작게, 가로) */}
      <div className="w-full shrink-0 overflow-hidden rounded-md border border-border bg-black md:w-80">
        {item.mp4_url ? (
          <video src={item.mp4_url} controls preload="metadata" className="aspect-video w-full" />
        ) : (
          <div className="flex aspect-video w-full items-center justify-center text-muted-foreground">
            <Music className="h-8 w-8" />
          </div>
        )}
      </div>

      {/* 본문 */}
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="truncate text-base font-semibold text-foreground">
            {item.title_kr || item.slug}
          </h3>
          {item.genre && <Badge variant="secondary">{item.genre}</Badge>}
          {item.mood && <Badge variant="outline">{item.mood}</Badge>}
        </div>

        {/* GPT 프롬프트 + 복사 */}
        <div className="rounded-md border border-border bg-secondary/30 p-3">
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              썸네일 GPT 프롬프트
            </span>
            <Button size="sm" variant="ghost" onClick={copyPrompt} className="h-7 gap-1.5">
              {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? "복사됨" : "복사"}
            </Button>
          </div>
          <p className="text-sm leading-relaxed text-foreground/90">{item.gpt_prompt}</p>
        </div>

        {/* 썸네일 업로드 + 공개 업로드 */}
        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => handleFile(e.target.files?.[0])}
          />
          <div
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault()
              handleFile(e.dataTransfer.files?.[0])
            }}
            className="flex h-16 w-28 cursor-pointer items-center justify-center overflow-hidden rounded-md border border-dashed border-border bg-secondary/20 text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
            title="클릭 또는 드래그&드롭"
          >
            {uploading ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : thumbUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={thumbUrl} alt="썸네일" className="h-full w-full object-cover" />
            ) : (
              <span className="flex flex-col items-center gap-1 text-[11px]">
                <Upload className="h-4 w-4" />
                썸네일
              </span>
            )}
          </div>

          {published ? (
            <a
              href={published}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-400 hover:underline"
            >
              <MonitorPlay className="h-4 w-4" /> 업로드됨 — 영상 보기
            </a>
          ) : (
            <Button
              onClick={publish}
              disabled={!hasThumb || publishing}
              className="gap-1.5"
              title={hasThumb ? "유튜브 공개 업로드" : "썸네일을 먼저 업로드하세요"}
            >
              {publishing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Globe className="h-4 w-4" />}
              유튜브 공개 업로드
            </Button>
          )}
          {!hasThumb && !published && (
            <span className="text-xs text-muted-foreground">썸네일 업로드 후 공개 가능</span>
          )}
        </div>
      </div>
    </div>
  )
}

export default function MusicQueuePage() {
  const [items, setItems] = useState<QueueItem[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    fetch("/api/music/queue")
      .then((r) => r.json())
      .then((d) => setItems(Array.isArray(d?.queue) ? d.queue : []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-auto p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-foreground">검토 대기 큐</h1>
          <p className="text-sm text-muted-foreground">
            자동 생성된 음악 영상 — 썸네일 업로드 후 공개 업로드할 수 있습니다.
          </p>
        </div>
        <Link
          href="/music/guide"
          className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground hover:bg-white/5 hover:text-foreground"
        >
          <BookOpen className="h-4 w-4" /> 테마 가이드
        </Link>
      </header>

      {loading ? (
        <div className="flex flex-1 items-center justify-center text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 text-muted-foreground">
          <Music className="h-10 w-10 opacity-40" />
          <p>검토 대기 중인 영상이 없습니다.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {items.map((item) => (
            <QueueCard key={item.mix_id} item={item} onChanged={load} />
          ))}
        </div>
      )}
    </div>
  )
}
