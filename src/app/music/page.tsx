"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import {
  Copy,
  Check,
  Upload,
  Globe,
  MonitorPlay,
  Loader2,
  BookOpen,
  Music,
  Trash2,
  Clapperboard,
  X,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

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
  const [deleting, setDeleting] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const remove = async () => {
    if (!window.confirm("이 영상을 큐에서 삭제할까요? 되돌릴 수 없습니다.")) return
    setDeleting(true)
    try {
      const res = await fetch(`/api/music/queue/${encodeURIComponent(item.mix_id)}`, {
        method: "DELETE",
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || "삭제 실패")
      toast.success("큐에서 삭제했습니다.")
      onChanged()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "삭제 실패")
      setDeleting(false)
    }
  }

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
    <div className="flex flex-col overflow-hidden rounded-lg border border-border bg-card">
      {/* 16:9 영상 + 썸네일 상태 배지 */}
      <div className="relative aspect-video w-full bg-black">
        {item.mp4_url ? (
          <video src={item.mp4_url} controls preload="metadata" className="h-full w-full" />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-muted-foreground">
            <Music className="h-8 w-8" />
          </div>
        )}
        <span
          className={cn(
            "absolute left-2 top-2 rounded-full px-2 py-0.5 text-[11px] font-medium",
            hasThumb ? "bg-emerald-500/20 text-emerald-300" : "bg-amber-500/20 text-amber-300",
          )}
        >
          {hasThumb ? "썸네일 ✓" : "썸네일 없음"}
        </span>
        {/* 삭제(위험 액션) — 깨진/못 쓰는 영상 정리 */}
        <button
          type="button"
          onClick={remove}
          disabled={deleting}
          title="큐에서 삭제"
          className="absolute right-2 top-2 inline-flex h-8 w-8 items-center justify-center rounded-full bg-black/50 text-red-400 hover:bg-red-500/30 hover:text-red-300 disabled:opacity-60"
        >
          {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
        </button>
      </div>

      {/* 본문 */}
      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="min-w-0 flex-1 truncate text-base font-semibold text-foreground">
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

        {/* 썸네일 업로드(점선 박스, 업로드 시 미리보기) */}
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
          className="flex min-h-[88px] cursor-pointer items-center justify-center overflow-hidden rounded-md border border-dashed border-border bg-secondary/20 text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
          title="클릭(모바일=사진첩) 또는 드래그&드롭"
        >
          {uploading ? (
            <Loader2 className="h-6 w-6 animate-spin" />
          ) : thumbUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={thumbUrl} alt="썸네일 미리보기" className="max-h-40 w-full object-contain" />
          ) : (
            <span className="flex flex-col items-center gap-1.5 py-3 text-xs">
              <Upload className="h-5 w-5" />
              썸네일 업로드
            </span>
          )}
        </div>

        {/* 공개 업로드(썸네일 게이트) */}
        {published ? (
          <a
            href={published}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-11 items-center justify-center gap-1.5 rounded-md bg-emerald-500/15 text-sm font-medium text-emerald-400 hover:bg-emerald-500/25"
          >
            <MonitorPlay className="h-4 w-4" /> 업로드 완료 — 영상 보기
          </a>
        ) : (
          <Button
            onClick={publish}
            disabled={!hasThumb || publishing}
            className={cn(
              "h-11 w-full gap-1.5",
              hasThumb && "bg-emerald-500 text-white hover:bg-emerald-500/90",
            )}
            title={hasThumb ? "유튜브 공개 업로드" : "썸네일을 먼저 업로드하세요"}
          >
            {publishing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Globe className="h-4 w-4" />}
            유튜브 공개 업로드
          </Button>
        )}
        {!hasThumb && !published && (
          <span className="text-center text-xs text-muted-foreground">
            썸네일 업로드 후 공개 가능
          </span>
        )}
      </div>
    </div>
  )
}

const TEST_MOODS: { key: string; label: string }[] = [
  { key: "citypop", label: "시티팝/드라이브" },
  { key: "cafe", label: "카페/재즈" },
  { key: "ballad", label: "이별/발라드" },
  { key: "workout", label: "운동/동기부여" },
  { key: "sleep", label: "수면/공부" },
]

export default function MusicQueuePage() {
  const [items, setItems] = useState<QueueItem[]>([])
  const [loading, setLoading] = useState(true)
  const [testMood, setTestMood] = useState("citypop")
  const [testLoading, setTestLoading] = useState(false)
  const [testVideo, setTestVideo] = useState<{ url: string; engine?: string } | null>(null)

  const load = useCallback(() => {
    fetch("/api/music/queue")
      .then((r) => r.json())
      .then((d) => setItems(Array.isArray(d?.queue) ? d.queue : []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [])

  const runTest = useCallback(async () => {
    setTestLoading(true)
    setTestVideo(null)
    try {
      const res = await fetch("/api/music/test-render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mood: testMood }),
      })
      const data = await res.json()
      if (!res.ok || !data?.video_url) throw new Error(data?.detail || "테스트 렌더 실패")
      setTestVideo({ url: data.video_url, engine: data.engine })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "테스트 렌더 실패")
    } finally {
      setTestLoading(false)
    }
  }, [testMood])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-auto p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3 pl-10 md:pl-0">
        <div>
          <h1 className="text-xl font-semibold text-foreground">검토 대기 큐</h1>
          <p className="text-sm text-muted-foreground">
            자동 생성된 음악 영상 — 썸네일 업로드 후 공개 업로드할 수 있습니다.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* 테스트 영상(#19) — 즉석 10초 렌더로 둥근 바·색상·곡 제목 확인(유튜브 X) */}
          <select
            value={testMood}
            onChange={(e) => setTestMood(e.target.value)}
            disabled={testLoading}
            className="h-9 rounded-lg border border-border bg-card px-2 text-sm text-foreground"
            title="테스트 영상 분위기(색상 매핑)"
          >
            {TEST_MOODS.map((m) => (
              <option key={m.key} value={m.key}>
                {m.label}
              </option>
            ))}
          </select>
          <Button onClick={runTest} disabled={testLoading} className="h-9 gap-1.5">
            {testLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Clapperboard className="h-4 w-4" />
            )}
            {testLoading ? "렌더 중…" : "테스트 영상"}
          </Button>
          <Link
            href="/music/guide"
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-border px-3 text-sm text-muted-foreground hover:bg-white/5 hover:text-foreground"
          >
            <BookOpen className="h-4 w-4" /> 테마 가이드
          </Link>
        </div>
      </header>

      {/* 테스트 영상 모달 — 재생/닫기(DB·유튜브 영향 0) */}
      {testVideo && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => setTestVideo(null)}
        >
          <div
            className="relative w-full max-w-3xl overflow-hidden rounded-xl border border-border bg-card"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
              <span className="text-sm font-medium text-foreground">
                테스트 영상 미리보기
                {testVideo.engine && (
                  <Badge variant="secondary" className="ml-2 align-middle">
                    {testVideo.engine}
                  </Badge>
                )}
              </span>
              <button
                type="button"
                onClick={() => setTestVideo(null)}
                className="inline-flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground hover:bg-white/5 hover:text-foreground"
                title="닫기"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <video src={testVideo.url} controls autoPlay className="aspect-video w-full bg-black" />
          </div>
        </div>
      )}

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
        // B안 세로 카드 그리드 — 데스크탑 2~3열, 모바일 1열 자동(auto-fit minmax).
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-[repeat(auto-fit,minmax(280px,1fr))]">
          {items.map((item) => (
            <QueueCard key={item.mix_id} item={item} onChanged={load} />
          ))}
        </div>
      )}
    </div>
  )
}
