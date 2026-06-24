"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { ArrowLeft, Loader2, Music2, Play, Pause, Clapperboard } from "lucide-react"
import { cn } from "@/lib/utils"
import { MUSIC_GENRES } from "@/lib/music-genres"
import { estimateProductionTime, fmtMinutes } from "@/lib/music"

interface LibraryItem {
  id: string
  audio_id: string
  title: string
  tags: string
  genre: string
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
const STATUS_FILTERS = [
  { key: "all", label: "전체" },
  { key: "unused", label: "미사용" },
  { key: "used", label: "사용됨" },
] as const

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
  const [status, setStatus] = useState<(typeof STATUS_FILTERS)[number]["key"]>("all")
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [playing, setPlaying] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const load = useCallback(() => {
    const qs = new URLSearchParams()
    if (genre !== "all") qs.set("genre", genre)
    if (status !== "all") qs.set("used", status === "used" ? "true" : "false")
    qs.set("limit", "200")
    fetch(`/api/music/library?${qs.toString()}`)
      .then((r) => r.json())
      .then((d) => setItems(Array.isArray(d?.items) ? d.items : []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [genre, status])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    fetch("/api/music/library/stats")
      .then((r) => r.json())
      .then((d) => setStats(Array.isArray(d?.stats) ? d.stats : []))
      .catch(() => setStats([]))
  }, [])

  const toggle = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const selectedCount = selected.size
  const est = useMemo(() => estimateProductionTime(Math.max(1, selectedCount)), [selectedCount])
  // 라이브러리는 Suno 스킵 → 제작시간에서 suno 단계 제외.
  const makeMinutes = Math.max(0, est.totalMinutes - est.sunoMinutes)

  const createVideo = useCallback(async () => {
    const ids = [...selected]
    if (ids.length === 0) return
    setCreating(true)
    try {
      const res = await fetch("/api/music/library/create-video", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ track_ids: ids }),
      })
      const data = await res.json()
      if (!res.ok || !data?.job_id) throw new Error(data?.detail || "영상 만들기 시작 실패")
      const jobId = data.job_id as string
      toast.success("영상 제작을 시작했습니다 — 검토 대기에서 진행 상황을 확인하세요.")
      await new Promise<void>((resolve) => {
        const tick = async () => {
          try {
            const sr = await fetch(`/api/music/library/create-video/status/${jobId}`)
            const sd = await sr.json()
            if (sd?.status === "done") {
              toast.success("영상 생성 완료 — 검토 대기에 추가되었습니다.")
              setSelected(new Set())
              load()
              resolve(); return
            }
            if (sd?.status === "error") {
              toast.error(sd?.error || "영상 생성 실패")
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
    }
  }, [selected, load])

  const genreChips = [{ id: "all", label: "전체" }, ...MUSIC_GENRES.map((g) => ({ id: g.id, label: g.label }))]

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-4xl flex-col gap-4 p-4 md:p-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Link href="/music" className="rounded-lg border border-border p-1.5 text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <h1 className="flex items-center gap-2 text-lg font-semibold text-foreground">
            <Music2 className="h-5 w-5 text-primary" /> 음원 라이브러리
          </h1>
        </div>
        <button
          type="button"
          onClick={createVideo}
          disabled={selectedCount === 0 || creating}
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3.5 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Clapperboard className="h-4 w-4" />}
          영상 만들기{selectedCount > 0 ? ` (${selectedCount}곡)` : ""}
        </button>
      </div>

      {/* 선택 요약 */}
      {selectedCount > 0 && (
        <div className="rounded-lg border border-primary/30 bg-primary/5 px-3 py-2 text-xs text-foreground">
          {selectedCount}곡 선택 · 예상 영상 {fmtMinutes(est.videoMinutes)} · 예상 제작 {fmtMinutes(makeMinutes)}
          <span className="ml-1 text-primary">· Suno 스킵(크레딧 0)</span>
          {selectedCount >= 3 && (
            <span className="ml-1 text-amber-400">· 3곡 이상은 제작이 길어질 수 있어요(분할 렌더 적용)</span>
          )}
        </div>
      )}

      {/* 필터 */}
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap gap-1.5">
          {genreChips.map((g) => (
            <button
              key={g.id}
              type="button"
              onClick={() => setGenre(g.id)}
              className={cn(
                "rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors",
                genre === g.id ? "border-primary/40 bg-primary/15 text-primary" : "border-border text-muted-foreground hover:border-primary/30 hover:text-foreground",
              )}
            >
              {g.label}
            </button>
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
            const isPlaying = playing === it.id
            return (
              <div
                key={it.id}
                className={cn(
                  "rounded-xl border bg-card p-2.5 transition-colors",
                  sel ? "border-primary/40 bg-primary/5" : "border-border",
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
                    onClick={() => setPlaying(isPlaying ? null : it.id)}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border text-muted-foreground hover:border-primary/40 hover:text-primary"
                    aria-label={isPlaying ? "정지" : "미리듣기"}
                  >
                    {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                  </button>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground">{it.title || "(제목 없음)"}</p>
                    <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
                      <span className="rounded-full bg-primary/15 px-1.5 text-primary">{GENRE_LABEL.get(it.genre) || it.genre || "기타"}</span>
                      <span className="tabular-nums">{fmtDuration(it.duration)}</span>
                      <span className={it.used ? "text-muted-foreground" : "text-emerald-400"}>{it.used ? "사용됨" : "미사용"}</span>
                    </div>
                  </div>
                </div>
                {isPlaying && it.play_url && (
                  <audio
                    src={it.play_url}
                    controls
                    autoPlay
                    onEnded={() => setPlaying(null)}
                    className="mt-2 h-9 w-full"
                  />
                )}
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
    </div>
  )
}
