"use client"

// 검토 대기 미리보기(#28) — 대시보드용. 백곰 '오늘의 콘텐츠' placeholder 대체.
// /api/music/queue 최신 2~3개를 작은 카드로(썸네일+제목+상태점), 클릭 → /music/queue.
import { useEffect, useState } from "react"
import Link from "next/link"
import { ChevronDown, Music } from "lucide-react"

interface QueueItem {
  slug: string
  mix_id: string
  title_kr?: string
  genre?: string
  thumbnail_url?: string | null
  thumbnail_r2_key?: string | null
}

export function MusicQueuePreview() {
  const [items, setItems] = useState<QueueItem[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    fetch("/api/music/queue")
      .then((r) => r.json())
      .then((d) => setItems(Array.isArray(d?.queue) ? d.queue.slice(0, 3) : []))
      .catch(() => setItems([]))
      .finally(() => setLoaded(true))
  }, [])

  return (
    <div className="rounded-xl border border-border bg-card p-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-foreground">검토 대기</h2>
        <Link
          href="/music/queue"
          className="flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-primary/5"
        >
          전체 보기
          <ChevronDown className="h-3.5 w-3.5" />
        </Link>
      </div>

      <div className="mt-2 flex flex-col gap-2">
        {loaded && items.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border/60 px-4 py-6 text-center text-xs text-muted-foreground">
            아직 검토할 영상이 없습니다. 매일 자동 생성됩니다.
          </div>
        ) : (
          items.map((it) => (
            <Link
              key={it.mix_id}
              href="/music/queue"
              className="flex items-center gap-2.5 rounded-lg border border-border p-2 transition-colors hover:border-primary/30 hover:bg-secondary/30"
            >
              <div className="flex h-10 w-16 shrink-0 items-center justify-center overflow-hidden rounded bg-secondary/40">
                {it.thumbnail_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={it.thumbnail_url} alt="" className="h-full w-full object-cover" />
                ) : (
                  <Music className="h-4 w-4 text-muted-foreground" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">{it.title_kr || it.slug}</p>
                {it.genre && <p className="truncate text-[11px] text-muted-foreground">{it.genre}</p>}
              </div>
              <span
                className={`h-2 w-2 shrink-0 rounded-full ${it.thumbnail_r2_key ? "bg-emerald-400" : "bg-amber-400"}`}
                title={it.thumbnail_r2_key ? "썸네일 있음" : "썸네일 없음"}
              />
            </Link>
          ))
        )}
      </div>
    </div>
  )
}
