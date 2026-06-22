"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import {
  ArrowLeft, Loader2, Music, Copy, Check, Upload, Globe, Trash2, Clapperboard, MonitorPlay,
} from "lucide-react"
import { cn } from "@/lib/utils"

interface VizSpec {
  primary_color?: string
  secondary_color?: string
  subtitle_en?: string
  scene_keywords?: string[]
}
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
  viz_spec?: VizSpec | null
  status?: string
  created_at?: string
}

const TEST_ID = "__test__"
const TEST_MOODS = [
  { key: "citypop", label: "시티팝/드라이브" },
  { key: "cafe", label: "카페/재즈" },
  { key: "ballad", label: "이별/발라드" },
  { key: "workout", label: "운동/동기부여" },
  { key: "sleep", label: "수면/공부" },
]

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

export default function MusicQueuePage() {
  const [items, setItems] = useState<QueueItem[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  // 테스트 영상(인라인)
  const [testMood, setTestMood] = useState("citypop")
  const [testLoading, setTestLoading] = useState(false)
  const [testVideo, setTestVideo] = useState<{ url: string; engine?: string } | null>(null)

  const load = useCallback(
    (keep?: string) => {
      fetch("/api/music/queue")
        .then((r) => r.json())
        .then((d) => {
          const list: QueueItem[] = Array.isArray(d?.queue) ? d.queue : []
          setItems(list)
          setSelectedId((cur) => keep ?? cur ?? (list[0]?.mix_id ?? null))
        })
        .catch(() => setItems([]))
        .finally(() => setLoading(false))
    },
    [],
  )

  useEffect(() => { load() }, [load])

  const runTest = useCallback(async () => {
    setTestLoading(true)
    setTestVideo(null)
    setSelectedId(TEST_ID)
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

  const selected = items.find((i) => i.mix_id === selectedId) || null
  const showTest = selectedId === TEST_ID

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-hidden p-4 md:p-6">
      <header className="flex items-center gap-3 pl-10 md:pl-0">
        <Link
          href="/music"
          className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground hover:bg-white/5 hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> 대시보드
        </Link>
        <div>
          <h1 className="text-xl font-semibold text-foreground">검토 대기</h1>
          <p className="text-sm text-muted-foreground">영상을 선택해 미리보고 썸네일·공개를 처리하세요.</p>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-3 md:grid md:grid-cols-[280px_minmax(0,1fr)]">
        {/* 좌측 리스트 — 모바일은 가로 스크롤(절반 이하), md+ 세로 */}
        <div className="flex shrink-0 gap-2 overflow-x-auto rounded-xl border border-border bg-card p-2 md:max-h-full md:flex-col md:overflow-x-visible md:overflow-y-auto">
          {/* + 테스트 영상 */}
          <div className="flex shrink-0 flex-col gap-1.5 rounded-lg border border-dashed border-border bg-secondary/20 p-2 md:w-auto">
            <select
              value={testMood}
              onChange={(e) => setTestMood(e.target.value)}
              disabled={testLoading}
              className="h-8 rounded-md border border-border bg-background px-1.5 text-xs text-foreground"
            >
              {TEST_MOODS.map((m) => (
                <option key={m.key} value={m.key}>{m.label}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={runTest}
              disabled={testLoading}
              className="inline-flex items-center justify-center gap-1.5 rounded-md bg-primary px-2.5 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90"
            >
              {testLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Clapperboard className="h-3.5 w-3.5" />}
              테스트 영상
            </button>
          </div>

          {loading ? (
            <div className="flex items-center gap-2 p-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> 불러오는 중…</div>
          ) : items.length === 0 ? (
            <div className="p-2 text-sm text-muted-foreground">검토 대기 영상이 없습니다.</div>
          ) : (
            items.map((it) => (
              <button
                key={it.mix_id}
                type="button"
                onClick={() => setSelectedId(it.mix_id)}
                className={cn(
                  "flex w-44 shrink-0 items-center gap-2 rounded-lg border px-2 py-1.5 text-left transition-colors md:w-auto",
                  selectedId === it.mix_id ? "border-primary/40 bg-primary/15" : "border-border hover:border-primary/30",
                )}
              >
                <div className="flex h-9 w-12 shrink-0 items-center justify-center overflow-hidden rounded bg-secondary/30">
                  {it.thumbnail_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={it.thumbnail_url} alt="" className="h-full w-full object-cover" />
                  ) : (
                    <Music className="h-4 w-4 text-muted-foreground" />
                  )}
                </div>
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{it.title_kr || it.slug}</span>
                <span className={cn("h-2 w-2 shrink-0 rounded-full", it.thumbnail_r2_key ? "bg-emerald-400" : "bg-amber-400")} />
              </button>
            ))
          )}
        </div>

        {/* 우측 상세 — 인라인 플레이어 + 도구 */}
        <div className="min-h-0 flex-1 overflow-auto rounded-xl border border-border bg-card p-4">
          {showTest ? (
            <TestDetail loading={testLoading} video={testVideo} />
          ) : selected ? (
            <QueueDetail key={selected.mix_id} item={selected} onChanged={load} />
          ) : (
            <div className="flex h-full min-h-[200px] flex-col items-center justify-center gap-2 text-muted-foreground">
              <Music className="h-10 w-10 opacity-40" />
              <p>좌측에서 영상을 선택하세요.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function TestDetail({ loading, video }: { loading: boolean; video: { url: string; engine?: string } | null }) {
  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-base font-semibold text-foreground">테스트 영상 (미리보기)</h2>
      <div className="relative aspect-video w-full overflow-hidden rounded-lg bg-black">
        {loading ? (
          <div className="flex h-full items-center justify-center text-muted-foreground"><Loader2 className="h-7 w-7 animate-spin" /></div>
        ) : video ? (
          <video src={video.url} controls autoPlay className="h-full w-full" />
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground"><Clapperboard className="h-8 w-8" /></div>
        )}
      </div>
      {video?.engine && <span className="text-xs text-muted-foreground">렌더 엔진: {video.engine} · 유튜브/큐에 저장되지 않습니다.</span>}
    </div>
  )
}

function QueueDetail({ item, onChanged }: { item: QueueItem; onChanged: (keep?: string) => void }) {
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
        onChanged(item.mix_id)
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
      const res = await fetch(`/api/music/queue/${encodeURIComponent(item.mix_id)}/publish`, { method: "POST" })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || "업로드 실패")
      setPublished(data.youtube_url)
      toast.success("유튜브 공개 업로드 완료")
      onChanged(item.mix_id)
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
    <div className="flex flex-col gap-4">
      {/* 인라인 플레이어 */}
      <div className="relative aspect-video w-full overflow-hidden rounded-lg bg-black">
        {item.mp4_url ? (
          <video src={item.mp4_url} controls preload="metadata" className="h-full w-full" />
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground"><Music className="h-8 w-8" /></div>
        )}
      </div>

      {/* 곡 정보 */}
      <div className="flex flex-col gap-2">
        <h2 className="text-base font-semibold text-foreground">{item.title_kr || item.slug}</h2>
        {viz?.subtitle_en && <p className="text-sm italic text-muted-foreground">{viz.subtitle_en}</p>}
        <div className="flex flex-wrap items-center gap-1.5">
          {item.genre && <span className="rounded-full bg-primary/15 px-2 py-0.5 text-xs text-primary">{item.genre}</span>}
          {item.mood && <span className="rounded-full bg-sky-500/15 px-2 py-0.5 text-xs text-sky-400">{item.mood}</span>}
          {viz?.primary_color && (
            <span className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">
              <span className="h-3 w-3 rounded-full" style={{ background: viz.primary_color }} />
              <span className="h-3 w-3 rounded-full" style={{ background: viz.secondary_color || viz.primary_color }} />
              색감
            </span>
          )}
        </div>
        {(viz?.scene_keywords?.length ?? 0) > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {viz!.scene_keywords!.map((k) => (
              <span key={k} className="rounded bg-secondary/40 px-1.5 py-0.5 text-[11px] text-muted-foreground">{k}</span>
            ))}
          </div>
        )}
      </div>

      {/* GPT 프롬프트 */}
      <div className="rounded-md border border-border bg-secondary/30 p-3">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">썸네일 GPT 프롬프트</span>
          <button type="button" onClick={copyPrompt} className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
            {copied ? "복사됨" : "복사"}
          </button>
        </div>
        <p className="text-sm leading-relaxed text-foreground/90">{item.gpt_prompt}</p>
      </div>

      {/* 썸네일 업로드 */}
      <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => handleFile(e.target.files?.[0])} />
      <div
        onClick={() => fileRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); handleFile(e.dataTransfer.files?.[0]) }}
        className="flex min-h-[88px] cursor-pointer items-center justify-center overflow-hidden rounded-md border border-dashed border-border bg-secondary/20 text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
      >
        {uploading ? (
          <Loader2 className="h-6 w-6 animate-spin" />
        ) : thumbUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={thumbUrl} alt="썸네일 미리보기" className="max-h-40 w-full object-contain" />
        ) : (
          <span className="flex flex-col items-center gap-1.5 py-3 text-xs"><Upload className="h-5 w-5" /> 깨끗한 이미지 업로드</span>
        )}
      </div>

      {/* 공개 + 삭제 */}
      <div className="flex items-center gap-2">
        {published ? (
          <a href={published} target="_blank" rel="noreferrer" className="inline-flex h-11 flex-1 items-center justify-center gap-1.5 rounded-md bg-emerald-500/15 text-sm font-medium text-emerald-400 hover:bg-emerald-500/25">
            <MonitorPlay className="h-4 w-4" /> 업로드 완료 — 영상 보기
          </a>
        ) : (
          <button
            type="button"
            onClick={publish}
            disabled={!hasThumb || publishing}
            className={cn("inline-flex h-11 flex-1 items-center justify-center gap-1.5 rounded-md text-sm font-medium", hasThumb ? "bg-emerald-600 text-white hover:opacity-90" : "border border-border text-muted-foreground")}
            title={hasThumb ? "유튜브 공개 업로드" : "이미지를 먼저 업로드하세요"}
          >
            {publishing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Globe className="h-4 w-4" />} 유튜브 공개 업로드
          </button>
        )}
        <button
          type="button"
          onClick={remove}
          disabled={deleting}
          className="inline-flex h-11 items-center justify-center rounded-md border border-red-500/30 px-3 text-red-400 hover:bg-red-500/15"
          title="큐에서 삭제"
        >
          {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
        </button>
      </div>
      {!hasThumb && !published && <span className="text-center text-xs text-muted-foreground">깨끗한 이미지 업로드 후 공개 가능</span>}
    </div>
  )
}
