"use client"

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import {
  ArrowLeft, Loader2, Music2, Play, Pause, Clapperboard,
  SkipForward, SkipBack, PictureInPicture2, ArrowUp, ArrowDown, X,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { MUSIC_GENRES } from "@/lib/music-genres"
import { ACTION_TAGS } from "@/lib/music-tags"
import { estimateProductionTime, fmtMinutes } from "@/lib/music"

interface LibraryItem {
  id: string
  audio_id: string
  title: string
  tags: string
  genre: string
  action: string
  duration: number | null
  used: boolean
  created_at?: string
  play_url: string
}

interface GenreStat {
  genre: string
  total: number
  unused: number
}

const GENRE_LABEL = new Map(MUSIC_GENRES.map((g) => [g.id, g.label]))
const ACTION_LABEL = new Map(ACTION_TAGS.map((t) => [t.id, t.label_kr]))
const STATUS_FILTERS = [
  { key: "all", label: "전체" },
  { key: "unused", label: "미사용" },
  { key: "used", label: "사용됨" },
] as const

// 가로 스크롤 + 스크롤바 숨김(globals.css 무수정 — arbitrary variant + inline style).
const HSCROLL = "flex flex-nowrap gap-1.5 overflow-x-auto [&::-webkit-scrollbar]:hidden"
const NOSCROLLBAR: React.CSSProperties = { scrollbarWidth: "none" }

function fmtDuration(sec: number | null): string {
  if (!sec || sec <= 0) return "--:--"
  const s = Math.round(sec)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`
}

export default function MusicLibraryPage() {
  const [items, setItems] = useState<LibraryItem[]>([])
  const [stats, setStats] = useState<GenreStat[]>([])
  const [loading, setLoading] = useState(true)
  const [genre, setGenre] = useState("all")
  const [action, setAction] = useState("all")
  const [status, setStatus] = useState<(typeof STATUS_FILTERS)[number]["key"]>("all")
  // B-5: 선택 순서 보존(배열). 믹스 순서 = 이 순서.
  const [selectedOrder, setSelectedOrder] = useState<string[]>([])
  const [creating, setCreating] = useState(false)
  const [jobId, setJobId] = useState<string | null>(null)
  const [cancelRequested, setCancelRequested] = useState(false)

  // B-3/B-4: 순차 재생 + PiP — 단일 <video>(오디오 전용) 공유.
  const videoRef = useRef<HTMLVideoElement>(null)
  const [queue, setQueue] = useState<string[]>([])
  const [qIdx, setQIdx] = useState(0)
  const [paused, setPaused] = useState(false)
  const [pipOn, setPipOn] = useState(false)

  const selected = useMemo(() => new Set(selectedOrder), [selectedOrder])
  const byId = useMemo(() => new Map(items.map((i) => [i.id, i])), [items])

  const load = useCallback(() => {
    const qs = new URLSearchParams()
    if (genre !== "all") qs.set("genre", genre)
    if (action !== "all") qs.set("action", action)
    if (status !== "all") qs.set("used", status === "used" ? "true" : "false")
    qs.set("limit", "200")
    fetch(`/api/music/library?${qs.toString()}`)
      .then((r) => r.json())
      .then((d) => setItems(Array.isArray(d?.items) ? d.items : []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [genre, action, status])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    fetch("/api/music/library/stats")
      .then((r) => r.json())
      .then((d) => setStats(Array.isArray(d?.stats) ? d.stats : []))
      .catch(() => setStats([]))
  }, [])

  // ── 선택 ───────────────────────────────────────────────────────────
  const toggle = useCallback((id: string) => {
    setSelectedOrder((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }, [])

  const filteredIds = useMemo(() => items.map((i) => i.id), [items])
  const allSelected = filteredIds.length > 0 && filteredIds.every((id) => selected.has(id))
  const toggleAll = useCallback(() => {
    setSelectedOrder((prev) => {
      const ids = items.map((i) => i.id)
      const allOn = ids.length > 0 && ids.every((id) => prev.includes(id))
      if (allOn) return prev.filter((id) => !ids.includes(id)) // 전체 해제(필터된 것만)
      const add = ids.filter((id) => !prev.includes(id)) // 누락분만 추가(순서 유지)
      return [...prev, ...add]
    })
  }, [items])

  const move = useCallback((id: string, dir: -1 | 1) => {
    setSelectedOrder((prev) => {
      const i = prev.indexOf(id)
      const j = i + dir
      if (i < 0 || j < 0 || j >= prev.length) return prev
      const next = [...prev]
      ;[next[i], next[j]] = [next[j], next[i]]
      return next
    })
  }, [])

  const selectedCount = selectedOrder.length
  const est = useMemo(() => estimateProductionTime(Math.max(1, selectedCount)), [selectedCount])
  const makeMinutes = Math.max(0, est.totalMinutes - est.sunoMinutes)

  // ── 재생(순차) ─────────────────────────────────────────────────────
  const currentId = queue[qIdx] ?? null
  const currentItem = currentId ? byId.get(currentId) : null

  const playSingle = useCallback((id: string) => {
    setQueue([id]); setQIdx(0); setPaused(false)
  }, [])
  const playSelected = useCallback(() => {
    if (selectedOrder.length === 0) return
    setQueue([...selectedOrder]); setQIdx(0); setPaused(false)
  }, [selectedOrder])
  const stopPlayer = useCallback(() => { setQueue([]); setQIdx(0); setPaused(false) }, [])
  const next = useCallback(() => setQIdx((i) => (i + 1 < queue.length ? i + 1 : i)), [queue.length])
  const prev = useCallback(() => setQIdx((i) => (i > 0 ? i - 1 : i)), [])

  // 현재곡 변경 → 로드·재생.
  useEffect(() => {
    const v = videoRef.current
    if (!v || !currentItem) return
    v.src = currentItem.play_url
    v.play().then(() => setPaused(false)).catch(() => {})
  }, [currentItem])

  const togglePlay = useCallback(() => {
    const v = videoRef.current
    if (!v) return
    if (v.paused) { v.play().catch(() => {}); setPaused(false) }
    else { v.pause(); setPaused(true) }
  }, [])

  const onEnded = useCallback(() => {
    setQIdx((i) => {
      if (i + 1 < queue.length) return i + 1
      // 마지막 곡 끝 → 정지.
      setQueue([])
      return 0
    })
  }, [queue.length])

  // PiP 지원 감지(데스크탑 표준 / iOS Safari webkit).
  const [pipSupported, setPipSupported] = useState(false)
  useEffect(() => {
    const v = videoRef.current
    const webkit = typeof (v as unknown as { webkitSupportsPresentationMode?: (m: string) => boolean })?.webkitSupportsPresentationMode === "function"
    setPipSupported(Boolean((typeof document !== "undefined" && document.pictureInPictureEnabled) || webkit))
  }, [currentItem])

  // PiP 종료 감지(표준 이벤트) → 버튼 상태 동기화.
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    const onLeave = () => setPipOn(false)
    const onEnter = () => setPipOn(true)
    v.addEventListener("leavepictureinpicture", onLeave)
    v.addEventListener("enterpictureinpicture", onEnter)
    return () => {
      v.removeEventListener("leavepictureinpicture", onLeave)
      v.removeEventListener("enterpictureinpicture", onEnter)
    }
  }, [])

  const togglePiP = useCallback(async () => {
    const v = videoRef.current as (HTMLVideoElement & { webkitSetPresentationMode?: (m: string) => void }) | null
    if (!v) return
    try {
      if (document.pictureInPictureElement) { await document.exitPictureInPicture(); setPipOn(false) }
      else if (v.requestPictureInPicture) { await v.requestPictureInPicture(); setPipOn(true) }
      else if (v.webkitSetPresentationMode) { v.webkitSetPresentationMode("picture-in-picture"); setPipOn(true) }
    } catch { /* 사용자 제스처 필요/미지원 — 무시 */ }
  }, [])

  // ── 영상 만들기(선택 순서대로 track_ids 전달) ───────────────────────
  const createVideo = useCallback(async () => {
    const ids = [...selectedOrder]
    if (ids.length === 0) return
    setCreating(true)
    setCancelRequested(false)
    setJobId(null)
    try {
      const res = await fetch("/api/music/library/create-video", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ track_ids: ids }),
      })
      const data = await res.json()
      if (!res.ok || !data?.job_id) throw new Error(data?.detail || "영상 만들기 시작 실패")
      const jid = data.job_id as string
      setJobId(jid)
      toast.success("영상 제작을 시작했습니다 — 검토 대기에서 진행 상황을 확인하세요.")
      await new Promise<void>((resolve) => {
        const tick = async () => {
          try {
            const sr = await fetch(`/api/music/library/create-video/status/${jid}`)
            const sd = await sr.json()
            if (sd?.status === "done") {
              toast.success("영상 생성 완료 — 검토 대기에 추가되었습니다.")
              setSelectedOrder([])
              load()
              resolve(); return
            }
            if (sd?.status === "error") { toast.error(sd?.error || "영상 생성 실패"); resolve(); return }
            if (sd?.status === "cancelled") {
              toast.message("생성이 취소되었습니다.")
              resolve(); return
            }
          } catch { /* 일시 실패는 다음 틱 재시도 */ }
          setTimeout(tick, 3000)
        }
        tick()
      })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "영상 만들기 시작 실패")
    } finally {
      setCreating(false)
      setJobId(null)
      setCancelRequested(false)
    }
  }, [selectedOrder, load])

  const handleCancel = useCallback(async () => {
    if (!jobId || cancelRequested) return
    setCancelRequested(true)
    try {
      await fetch(`/api/music/library/create-video/${jobId}/cancel`, { method: "POST" })
    } catch { /* 취소 실패는 무시 */ }
  }, [jobId, cancelRequested])

  const actionChips = [{ id: "all", label: "전체" }, ...ACTION_TAGS.map((t) => ({ id: t.id, label: t.label_kr }))]
  const genreChips = [{ id: "all", label: "전체" }, ...MUSIC_GENRES.map((g) => ({ id: g.id, label: g.label }))]
  const playerActive = queue.length > 0 && Boolean(currentItem)

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-4xl flex-col gap-4 p-4 pb-24 md:p-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Link href="/music" className="shrink-0 rounded-lg border border-border p-1.5 text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <h1 className="flex items-center gap-2 truncate text-lg font-semibold text-foreground">
            <Music2 className="h-5 w-5 shrink-0 text-primary" /> 음원 라이브러리
          </h1>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {creating && jobId && (
            <button
              type="button"
              onClick={handleCancel}
              disabled={cancelRequested}
              className="inline-flex items-center gap-1.5 rounded-md border border-red-500/40 px-2.5 py-1.5 text-[11px] font-medium text-red-400 hover:bg-red-500/10 disabled:opacity-60"
            >
              {cancelRequested ? "취소 요청됨…" : "✕ 생성 취소"}
            </button>
          )}
          <button
            type="button"
            onClick={createVideo}
            disabled={selectedCount === 0 || creating}
            className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg bg-primary px-3.5 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Clapperboard className="h-4 w-4" />}
            영상 만들기{selectedCount > 0 ? ` (${selectedCount})` : ""}
          </button>
        </div>
      </div>

      {/* 필터 — 어떨때 + 장르 + 상태 */}
      <div className="flex flex-col gap-2">
        <div className={HSCROLL} style={NOSCROLLBAR}>
          {actionChips.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => setAction(a.id)}
              className={cn(
                "shrink-0 whitespace-nowrap rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors",
                action === a.id ? "border-primary/40 bg-primary/15 text-primary" : "border-border text-muted-foreground hover:border-primary/30 hover:text-foreground",
              )}
            >
              {a.label}
            </button>
          ))}
        </div>
        <div className={HSCROLL} style={NOSCROLLBAR}>
          {genreChips.map((g) => (
            <Fragment key={g.id}>
              {g.id === "hotel_lobby" && (
                <span className="shrink-0 self-center whitespace-nowrap px-1 text-[10px] text-muted-foreground/60">── 장소 BGM ──</span>
              )}
              <button
                type="button"
                onClick={() => setGenre(g.id)}
                className={cn(
                  "shrink-0 whitespace-nowrap rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors",
                  genre === g.id ? "border-primary/40 bg-primary/15 text-primary" : "border-border text-muted-foreground hover:border-primary/30 hover:text-foreground",
                )}
              >
                {g.label}
              </button>
            </Fragment>
          ))}
        </div>
        <div className="flex gap-1.5">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s.key}
              type="button"
              onClick={() => setStatus(s.key)}
              className={cn(
                "rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors",
                status === s.key ? "border-primary/40 bg-primary/15 text-primary" : "border-border text-muted-foreground hover:border-primary/30 hover:text-foreground",
              )}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* 선택 요약 + 순서 지정(B-5) */}
      {selectedCount > 0 && (
        <div className="flex flex-col gap-2 rounded-lg border border-primary/30 bg-primary/5 p-3">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-foreground">
            <span className="font-medium">{selectedCount}곡 선택</span>
            <span className="text-muted-foreground">· 예상 영상 {fmtMinutes(est.videoMinutes)} · 예상 제작 {fmtMinutes(makeMinutes)}</span>
            <span className="text-primary">· Suno 스킵(크레딧 0)</span>
            {selectedCount >= 3 && <span className="text-amber-400">· 3곡 이상은 제작이 길어질 수 있어요</span>}
            <button type="button" onClick={playSelected} className="ml-auto inline-flex items-center gap-1 rounded-md border border-primary/40 px-2 py-1 text-[11px] text-primary hover:bg-primary/10">
              <Play className="h-3 w-3" /> 선택곡 순차 재생
            </button>
          </div>
          {/* 순서 목록(↑↓) — 이 순서대로 믹스 */}
          <ol className="flex flex-col gap-1">
            {selectedOrder.map((id, idx) => {
              const it = byId.get(id)
              if (!it) return null
              return (
                <li key={id} className="flex items-center gap-2 rounded-md bg-background/40 px-2 py-1 text-xs">
                  <span className="w-5 shrink-0 text-center tabular-nums text-muted-foreground">{idx + 1}</span>
                  <span className="min-w-0 flex-1 truncate text-foreground">{it.title || "(제목 없음)"}</span>
                  <button type="button" onClick={() => move(id, -1)} disabled={idx === 0} className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-30" aria-label="위로">
                    <ArrowUp className="h-3.5 w-3.5" />
                  </button>
                  <button type="button" onClick={() => move(id, 1)} disabled={idx === selectedOrder.length - 1} className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-30" aria-label="아래로">
                    <ArrowDown className="h-3.5 w-3.5" />
                  </button>
                  <button type="button" onClick={() => toggle(id)} className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-red-400" aria-label="선택 해제">
                    <X className="h-3.5 w-3.5" />
                  </button>
                </li>
              )
            })}
          </ol>
        </div>
      )}

      {/* 전체 선택(B-2) */}
      {items.length > 0 && (
        <label className="flex items-center gap-2 px-1 text-xs text-muted-foreground">
          <input type="checkbox" checked={allSelected} onChange={toggleAll} className="h-4 w-4 accent-primary" />
          전체 선택 ({items.length}곡)
        </label>
      )}

      {/* 목록 */}
      <div className="flex flex-col gap-1.5">
        {loading ? (
          <p className="py-10 text-center text-sm text-muted-foreground">불러오는 중…</p>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center gap-1 rounded-lg border border-dashed border-border/60 py-10 text-center">
            <Music2 className="h-6 w-6 text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground">적립된 곡이 없습니다.</p>
          </div>
        ) : (
          items.map((it) => {
            const sel = selected.has(it.id)
            const isCurrent = currentId === it.id
            return (
              <div
                key={it.id}
                className={cn(
                  "rounded-xl border bg-card p-2.5 transition-colors",
                  isCurrent ? "border-primary/60 bg-primary/10" : sel ? "border-primary/40 bg-primary/5" : "border-border",
                )}
              >
                <div className="flex items-center gap-2.5">
                  <input
                    type="checkbox"
                    checked={sel}
                    onChange={() => toggle(it.id)}
                    className="h-4 w-4 shrink-0 accent-primary"
                    aria-label={`${it.title} 선택`}
                  />
                  <button
                    type="button"
                    onClick={() => (isCurrent ? togglePlay() : playSingle(it.id))}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border text-muted-foreground hover:border-primary/40 hover:text-primary"
                    aria-label={isCurrent && !paused ? "일시정지" : "재생"}
                  >
                    {isCurrent && !paused ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                  </button>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground">{it.title || "(제목 없음)"}</p>
                    <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                      {it.action && <span className="rounded-full bg-emerald-500/15 px-1.5 text-emerald-400">{ACTION_LABEL.get(it.action) || it.action}</span>}
                      <span className="rounded-full bg-primary/15 px-1.5 text-primary">{GENRE_LABEL.get(it.genre) || it.genre || "기타"}</span>
                      <span className="tabular-nums">{fmtDuration(it.duration)}</span>
                      <span className={it.used ? "text-muted-foreground" : "text-emerald-400"}>{it.used ? "사용됨" : "미사용"}</span>
                    </div>
                  </div>
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* 적립 현황 */}
      {stats.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-3 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">📊 적립 현황: </span>
          {stats.map((s, i) => (
            <span key={s.genre}>
              {i > 0 && " / "}
              {GENRE_LABEL.get(s.genre) || s.genre} {s.total}곡
              <span className="text-emerald-400">(미사용 {s.unused})</span>
            </span>
          ))}
        </div>
      )}

      {/* 공유 오디오 플레이어(<video> = iOS PiP 워크어라운드). 화면 밖 1px(렌더 유지 → PiP 가능). */}
      <video
        ref={videoRef}
        playsInline
        onEnded={onEnded}
        onPlay={() => setPaused(false)}
        onPause={() => setPaused(true)}
        style={{ position: "fixed", width: 1, height: 1, bottom: 0, left: 0, opacity: 0, pointerEvents: "none" }}
      />

      {/* 미니 플레이어(B-3) — sticky 하단 고정 */}
      {playerActive && currentItem && (
        <div className="sticky bottom-0 z-20 -mx-4 mt-2 flex items-center gap-2 border-t border-border bg-card/95 px-4 py-2 backdrop-blur md:-mx-6 md:px-6">
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-medium text-foreground">{currentItem.title || "(제목 없음)"}</p>
            <p className="truncate text-[10px] text-muted-foreground">
              {queue.length > 1 ? `${qIdx + 1} / ${queue.length} · ` : ""}{GENRE_LABEL.get(currentItem.genre) || currentItem.genre || "기타"}
            </p>
          </div>
          {queue.length > 1 && (
            <button type="button" onClick={prev} disabled={qIdx === 0} className="rounded-full p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30" aria-label="이전 곡">
              <SkipBack className="h-4 w-4" />
            </button>
          )}
          <button type="button" onClick={togglePlay} className="rounded-full bg-primary p-2 text-primary-foreground hover:opacity-90" aria-label={paused ? "재생" : "일시정지"}>
            {paused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
          </button>
          {queue.length > 1 && (
            <button type="button" onClick={next} disabled={qIdx >= queue.length - 1} className="rounded-full p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30" aria-label="다음 곡">
              <SkipForward className="h-4 w-4" />
            </button>
          )}
          {pipSupported && (
            <button type="button" onClick={togglePiP} className={cn("rounded-full p-1.5 hover:text-foreground", pipOn ? "text-primary" : "text-muted-foreground")} aria-label="PiP(작은 창)">
              <PictureInPicture2 className="h-4 w-4" />
            </button>
          )}
          <button type="button" onClick={stopPlayer} className="rounded-full p-1.5 text-muted-foreground hover:text-foreground" aria-label="닫기">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  )
}
