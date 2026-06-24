"use client"

import { useCallback, useRef, useState } from "react"
import { toast } from "sonner"
import { Loader2, Music, Copy, Check, Upload, Globe, Trash2, MonitorPlay, Languages, ChevronDown, ChevronUp, RefreshCw } from "lucide-react"
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
  show_playlist?: boolean // #39 영상별 PLAY LIST 표시(미지정=표시)
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

// #38 클라이언트 압축 — 최대 2560px·JPEG 품질 0.95(1080p 출력엔 충분, 선명도↑).
// 413 방지: 결과 dataURL 이 Vercel 서버리스 본문 한도(4.5MB) 안에 들도록 품질을 단계적
// 하향(아주 디테일한 대용량 이미지만 해당). canvas 미지원/실패 시 원본 dataURL 폴백.
const _UPLOAD_MAX_DATAURL = 4_000_000 // ≈4MB(Vercel 4.5MB 본문 한도 내, JSON 오버헤드 여유)
async function compressImage(file: File, maxPx = 2560, quality = 0.95): Promise<string> {
  try {
    const dataUrl = await fileToDataUrl(file)
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const el = new Image()
      el.onload = () => resolve(el)
      el.onerror = reject
      el.src = dataUrl
    })
    const scale = Math.min(1, maxPx / Math.max(img.width, img.height))
    const w = Math.round(img.width * scale)
    const h = Math.round(img.height * scale)
    const canvas = document.createElement("canvas")
    canvas.width = w
    canvas.height = h
    const ctx = canvas.getContext("2d")
    if (!ctx) return dataUrl
    ctx.drawImage(img, 0, 0, w, h)
    // 품질 0.95 부터 시작해, 본문 한도를 넘으면 0.07 씩 낮춰 한도 안으로(최저 0.5).
    let q = quality
    let out = canvas.toDataURL("image/jpeg", q)
    while (out.length > _UPLOAD_MAX_DATAURL && q > 0.5) {
      q = Math.round((q - 0.07) * 100) / 100
      out = canvas.toDataURL("image/jpeg", q)
    }
    return out
  } catch {
    return fileToDataUrl(file)
  }
}

// 카드 분리감 강화(#28) — 보더 + 미세 그림자 + ring 으로 각 카드를 독립 단위로.
const cardClass = "flex flex-col overflow-hidden rounded-xl border border-border bg-card shadow-md ring-1 ring-black/5"

// 빠른 테스트 카드(임시, 보라 점선) — 합성 음원 10초. DB·유튜브 미저장.
export function TestCard({ loading, video }: { loading: boolean; video: { url: string; engine?: string } | null }) {
  return (
    <div className={cn(cardClass, "border-dashed border-primary/40")}>
      <div className="relative aspect-video w-full bg-black">
        {loading ? (
          <div className="flex h-full items-center justify-center text-muted-foreground"><Loader2 className="h-7 w-7 animate-spin" /></div>
        ) : video ? (
          <video src={video.url} controls autoPlay className="h-full w-full" />
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground"><MonitorPlay className="h-7 w-7" /></div>
        )}
        <span className="absolute left-2 top-2 rounded-full bg-primary/20 px-2 py-0.5 text-[11px] font-semibold text-primary">테스트 10초</span>
      </div>
      <div className="flex flex-col gap-1 p-3">
        <span className="text-sm font-semibold text-foreground">빠른 테스트</span>
        <span className="text-xs text-muted-foreground">
          {video?.engine ? `렌더 엔진: ${video.engine} · ` : ""}DB·유튜브에 저장되지 않습니다.
        </span>
      </div>
    </div>
  )
}

// 수동 영상 생성 진행 카드(#26) — 완료되면 사라지고 검토 큐 일반 카드로 등장(테스트 배지 X).
export function ManualProgressCard({ step }: { step: string }) {
  const STEPS = ["주제", "음원", "가사", "렌더", "완료"]
  const idx = Math.max(0, STEPS.indexOf(step))
  return (
    <div className={cardClass}>
      <div className="relative flex aspect-video w-full flex-col items-center justify-center gap-2 bg-black text-muted-foreground">
        <Loader2 className="h-7 w-7 animate-spin text-primary" />
        <span className="text-xs text-foreground/90">{step}…</span>
      </div>
      <div className="flex flex-col gap-2 p-3">
        <span className="text-sm font-semibold text-foreground">수동 영상 생성 중</span>
        <div className="flex flex-wrap items-center gap-1">
          {STEPS.map((s, i) => (
            <span
              key={s}
              className={cn(
                "rounded px-1.5 py-0.5 text-[10px] font-medium",
                i < idx ? "bg-emerald-500/15 text-emerald-400" : i === idx ? "bg-primary/15 text-primary" : "bg-secondary/40 text-muted-foreground",
              )}
            >
              {s}
            </span>
          ))}
        </div>
        <span className="text-xs text-muted-foreground">진짜 음원 1곡 · 최대 30분 소요 가능. 완료 시 검토 큐에 자동 추가됩니다.</span>
      </div>
    </div>
  )
}

export function MusicQueueCard({ item, onChanged }: { item: QueueItem; onChanged: (keep?: string) => void }) {
  const [copied, setCopied] = useState(false)
  const [thumbUrl, setThumbUrl] = useState<string | null>(item.thumbnail_url ?? null)
  const [needsRerender, setNeedsRerender] = useState(false)
  const [rerendering, setRerendering] = useState(false)
  const [rerenderStep, setRerenderStep] = useState("준비")
  const [uploading, setUploading] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [published, setPublished] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  // #39 영상별 PLAY LIST 표시 토글(미지정=표시). 변경 시 즉시 DB 저장 → [재렌더]로 반영.
  const [showPlaylist, setShowPlaylist] = useState(item.show_playlist ?? true)
  const [savingPl, setSavingPl] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const viz = item.viz_spec || undefined

  const togglePlaylist = useCallback(async () => {
    const next = !showPlaylist
    setSavingPl(true)
    setShowPlaylist(next) // 낙관적 반영
    try {
      const res = await fetch(`/api/music/queue/${encodeURIComponent(item.mix_id)}/show-playlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ show_playlist: next }),
      })
      const d = await res.json().catch(() => ({}))
      if (!res.ok || !d?.ok) throw new Error(d?.detail || "저장 실패")
      setNeedsRerender(true) // 영상에 반영하려면 재렌더 필요
      toast.success(`PLAY LIST 표시 ${next ? "ON" : "OFF"} — [재렌더]로 영상에 반영하세요.`)
    } catch (e) {
      setShowPlaylist(!next) // 롤백
      toast.error(e instanceof Error ? e.message : "저장 실패")
    } finally {
      setSavingPl(false)
    }
  }, [showPlaylist, item.mix_id])

  const copyPrompt = async () => {
    // #49: 장르별 풀에서 매번 새 프롬프트를 받아 복사(같은 장르라도 다른 컷). 실패 시 저장값 폴백.
    let text = item.gpt_prompt || ""
    try {
      if (item.genre) {
        const r = await fetch(`/api/music/genre-prompt?genre=${encodeURIComponent(item.genre)}`)
        const d = await r.json().catch(() => null)
        if (d?.prompt) text = d.prompt as string
      }
    } catch { /* 네트워크 실패 → 저장된 gpt_prompt 폴백 */ }
    try {
      await navigator.clipboard.writeText(text)
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
        const dataUrl = await compressImage(file) // #38: 2560px·JPEG 0.95(선명도↑) + 413 자동 방지
        const res = await fetch(`/api/music/queue/${encodeURIComponent(item.mix_id)}/thumbnail`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ image_base64: dataUrl, slug: item.slug }),
        })
        const data = await res.json().catch(() => ({}))
        if (res.status === 413) throw new Error("이미지가 너무 큽니다. 더 작은 이미지를 사용하거나 잠시 후 다시 시도하세요.")
        if (!res.ok) throw new Error(data?.detail || "업로드 실패")
        setThumbUrl(`${data.thumbnail_url}?v=${Date.now()}`)
        // #33 A: 오버레이 미리보기 제거 → '재렌더 대기'. [재렌더] 눌러야 실제 영상에 반영.
        setNeedsRerender(true)
        toast.success("이미지 업로드됨 — [재렌더]를 눌러 영상에 반영하세요.")
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

  const rerender = async () => {
    setRerendering(true)
    setRerenderStep("준비")
    try {
      const res = await fetch(`/api/music/queue/${encodeURIComponent(item.mix_id)}/rerender`, { method: "POST" })
      const data = await res.json()
      if (!res.ok || !data?.job_id) throw new Error(data?.detail || "재렌더 시작 실패")
      const jobId = data.job_id as string
      await new Promise<void>((resolve) => {
        const tick = async () => {
          try {
            const sr = await fetch(`/api/music/queue/rerender/status/${jobId}`)
            const sd = await sr.json()
            if (sd?.step) setRerenderStep(sd.step)
            if (sd?.status === "done") {
              toast.success("재렌더 완료 — 영상이 갱신되었습니다.")
              setNeedsRerender(false)
              onChanged(item.mix_id) // 큐 새로고침 → 새 mp4_url 반영
              resolve(); return
            }
            if (sd?.status === "error") { toast.error(sd?.error || "재렌더 실패"); resolve(); return }
          } catch { /* 다음 틱 재시도 */ }
          setTimeout(tick, 4000)
        }
        tick()
      })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "재렌더 실패")
    } finally {
      setRerendering(false)
    }
  }

  const removeImage = async () => {
    try {
      const res = await fetch(`/api/music/queue/${encodeURIComponent(item.mix_id)}/thumbnail`, { method: "DELETE" })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || "이미지 제거 실패")
      setThumbUrl(null)
      setNeedsRerender(false)
      toast.success("이미지 제거됨 — 다시 업로드할 수 있습니다.")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "이미지 제거 실패")
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
        {/* #33 A: 재렌더 진행 오버레이(실제 영상으로 갱신 중) */}
        {rerendering && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/70 text-white">
            <Loader2 className="h-7 w-7 animate-spin" />
            <span className="text-xs">재렌더 중… {rerenderStep} (3~5분)</span>
          </div>
        )}
        <span className={cn("absolute left-2 top-2 rounded-full px-2 py-0.5 text-[11px] font-medium",
          needsRerender ? "bg-sky-500/20 text-sky-300" : hasThumb ? "bg-emerald-500/20 text-emerald-300" : "bg-amber-500/20 text-amber-300")}>
          {needsRerender ? "재렌더 대기" : hasThumb ? "썸네일 ✓" : "썸네일 없음"}
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

        {/* #39 영상별 PLAY LIST 표시 토글 — 싱글곡 OFF, 플레이리스트 ON. 변경 후 [재렌더]로 반영. */}
        <button
          type="button"
          onClick={togglePlaylist}
          disabled={savingPl}
          role="switch"
          aria-checked={showPlaylist}
          title="이 영상에 'PLAY LIST' 텍스트를 표시할지 — 변경 후 [재렌더]로 영상에 반영"
          className="flex items-center justify-between gap-2 rounded-md border border-border px-2.5 py-2 text-xs font-medium transition-colors hover:border-primary/40 disabled:opacity-60"
        >
          <span className="text-muted-foreground">PLAY LIST 표시</span>
          <span className="flex items-center gap-1.5">
            <span className={showPlaylist ? "text-emerald-400" : "text-muted-foreground"}>{showPlaylist ? "ON" : "OFF"}</span>
            <span className={`relative h-4 w-7 shrink-0 rounded-full transition-colors ${showPlaylist ? "bg-emerald-600" : "bg-secondary"}`}>
              <span className={`absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all ${showPlaylist ? "left-3.5" : "left-0.5"}`} />
            </span>
          </span>
        </button>

        {/* #33 A/C: 재렌더(올린 이미지로 실제 영상 갱신) + 이미지 제거 */}
        {hasThumb && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={rerender}
              disabled={rerendering}
              className={cn(
                "inline-flex h-9 flex-1 items-center justify-center gap-1.5 rounded-md text-xs font-medium disabled:opacity-60",
                needsRerender ? "bg-sky-600 text-white hover:opacity-90" : "border border-border text-muted-foreground hover:border-primary/40",
              )}
              title="올린 이미지로 실제 영상을 다시 렌더(유튜브에 올라갈 형태 그대로)"
            >
              {rerendering ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              {needsRerender ? "재렌더 (대기 중)" : "재렌더"}
            </button>
            <button
              type="button"
              onClick={removeImage}
              disabled={rerendering}
              className="inline-flex h-9 items-center justify-center rounded-md border border-red-500/30 px-2.5 text-red-400 hover:bg-red-500/15"
              title="이미지 제거(다시 업로드 가능)"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        {/* #32 다국어 검수 — 펼쳐서 언어별 제목·설명·가사 확인/수정 */}
        <MultilangPanel mixId={item.mix_id} />

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

// #32 다국어 검수 패널 — [다국어 ▼] 펼침 → 언어 탭(KR EN JA ZH ES PT AR HI TH TL VI) →
// 선택 언어 제목·설명·가사 표시·수정 → 저장. 게시 시 저장된 데이터로 업로드.
const ML_TABS: { key: string; label: string }[] = [
  { key: "ko", label: "한국어" }, { key: "en", label: "영어" }, { key: "ja", label: "일본어" },
  { key: "zh", label: "중국어" }, { key: "es", label: "스페인어" }, { key: "pt", label: "포르투갈어" },
  { key: "ar", label: "아랍어" }, { key: "hi", label: "힌디어" }, { key: "th", label: "태국어" },
  { key: "tl", label: "필리핀어" }, { key: "vi", label: "베트남어" },
]

interface Localizations {
  source_lang?: string
  meta?: Record<string, { title?: string; description?: string }>
  lyrics?: Record<string, string>
  hashtags?: string[]
}

function MultilangPanel({ mixId }: { mixId: string }) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [ml, setMl] = useState<Localizations | null>(null)
  const [lang, setLang] = useState("ko")

  const ensure = useCallback(async () => {
    if (ml) return
    setLoading(true)
    try {
      const res = await fetch(`/api/music/queue/${encodeURIComponent(mixId)}/localize`, { method: "POST" })
      const data = await res.json()
      if (!res.ok || !data?.localizations) throw new Error(data?.detail || "다국어 생성 실패")
      setMl(data.localizations)
      setLang(data.localizations.source_lang || "ko")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "다국어 생성 실패")
    } finally {
      setLoading(false)
    }
  }, [ml, mixId])

  const toggle = () => {
    const next = !open
    setOpen(next)
    if (next) ensure()
  }

  const updateMeta = (field: "title" | "description", v: string) => {
    setMl((cur) => {
      if (!cur) return cur
      const meta = { ...(cur.meta || {}) }
      meta[lang] = { ...(meta[lang] || {}), [field]: v }
      return { ...cur, meta }
    })
  }
  const updateLyrics = (v: string) => {
    setMl((cur) => (cur ? { ...cur, lyrics: { ...(cur.lyrics || {}), [lang]: v } } : cur))
  }

  const save = async () => {
    if (!ml) return
    setSaving(true)
    try {
      const res = await fetch(`/api/music/queue/${encodeURIComponent(mixId)}/localize`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ localizations: ml }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data?.detail || "저장 실패")
      toast.success("다국어 수정사항 저장됨")
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "저장 실패")
    } finally {
      setSaving(false)
    }
  }

  const meta = ml?.meta?.[lang] || {}
  const lyrics = ml?.lyrics?.[lang] ?? ""

  return (
    <div className="rounded-md border border-border bg-secondary/20">
      <button
        type="button"
        onClick={toggle}
        className="flex w-full items-center justify-between gap-2 px-2.5 py-2 text-xs font-medium text-muted-foreground hover:text-foreground"
      >
        <span className="flex items-center gap-1.5"><Languages className="h-3.5 w-3.5" /> 다국어 (10개 언어)</span>
        {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
      </button>

      {open && (
        <div className="border-t border-border p-2.5">
          {loading ? (
            <div className="flex items-center gap-2 py-3 text-xs text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> 10개 언어 번역 중…</div>
          ) : !ml ? (
            <p className="py-2 text-xs text-muted-foreground">다국어 데이터를 불러오지 못했습니다.</p>
          ) : (
            <div className="flex flex-col gap-2">
              {/* 언어 탭 */}
              <div className="flex flex-wrap gap-1">
                {ML_TABS.map((t) => (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => setLang(t.key)}
                    className={cn(
                      "rounded px-1.5 py-0.5 text-[11px] font-medium transition-colors",
                      lang === t.key ? "bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              {/* 제목 */}
              <label className="text-[10px] font-medium uppercase text-muted-foreground">제목</label>
              <input
                value={meta.title ?? ""}
                onChange={(e) => updateMeta("title", e.target.value)}
                className="rounded border border-border bg-background px-2 py-1 text-xs text-foreground"
                placeholder="(번역 없음)"
              />
              {/* 설명 */}
              <label className="text-[10px] font-medium uppercase text-muted-foreground">설명</label>
              <textarea
                value={meta.description ?? ""}
                onChange={(e) => updateMeta("description", e.target.value)}
                rows={3}
                className="resize-y rounded border border-border bg-background px-2 py-1 text-xs text-foreground"
                placeholder="(번역 없음)"
              />
              {/* 가사 */}
              <label className="text-[10px] font-medium uppercase text-muted-foreground">가사</label>
              <textarea
                value={lyrics}
                onChange={(e) => updateLyrics(e.target.value)}
                rows={4}
                className="resize-y rounded border border-border bg-background px-2 py-1 text-xs text-foreground"
                placeholder="(가사 없음)"
              />
              {(ml.hashtags?.length ?? 0) > 0 && (
                <p className="truncate text-[10px] text-muted-foreground">{ml.hashtags!.join(" ")}</p>
              )}
              <button
                type="button"
                onClick={save}
                disabled={saving}
                className="inline-flex items-center justify-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium hover:border-primary/40 disabled:opacity-60"
              >
                {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} 수정사항 저장
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
