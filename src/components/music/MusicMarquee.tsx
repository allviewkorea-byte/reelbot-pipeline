"use client"

// 최근 업로드 음악 영상 마퀴 — 백곰 RecentVideosMarquee 구조·className 1:1 복제
// (직접 import 금지). 음악 영상은 16:9 가로라 카드 비율만 aspect-video 로 조정.
import { useEffect, useState } from "react"
import { Film, Loader2 } from "lucide-react"

interface RecentVideo {
  mix_id: string
  title_kr?: string
  genre?: string
  youtube_url?: string
  thumbnail_url?: string | null
}

function VideoCard({ v }: { v: RecentVideo }) {
  const inner = (
    <div className="mr-4 flex h-full shrink-0 flex-col items-center">
      {/* 16:9 가로 썸네일(음악) — 높이 확정 후 aspect-video 로 폭 파생 */}
      <div className="flex aspect-video h-[calc(100%_-_4.5rem)] w-auto items-center justify-center overflow-hidden rounded-lg border border-border/60 bg-secondary/50">
        {v.thumbnail_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={v.thumbnail_url} alt={v.title_kr || ""} className="h-full w-full object-cover" />
        ) : (
          <Film className="h-10 w-10 text-muted-foreground" />
        )}
      </div>
      <div className="mt-2 h-16 w-0 min-w-full shrink-0 overflow-hidden px-0.5">
        <p className="line-clamp-2 text-sm font-medium leading-snug text-foreground">{v.title_kr || v.mix_id}</p>
        <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
          {v.genre && <span>{v.genre}</span>}
          <span>유튜브</span>
        </div>
      </div>
    </div>
  )
  return v.youtube_url ? (
    <a href={v.youtube_url} target="_blank" rel="noreferrer">{inner}</a>
  ) : (
    inner
  )
}

export function MusicMarquee() {
  const [videos, setVideos] = useState<RecentVideo[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    fetch("/api/music/recent")
      .then((r) => r.json())
      .then((d) => {
        if (!active) return
        setVideos(Array.isArray(d?.videos) ? (d.videos as RecentVideo[]) : [])
      })
      .catch(() => {})
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [])

  return (
    <div className="flex min-h-[300px] flex-1 flex-col rounded-xl border border-border bg-card p-3 md:min-h-0">
      <div className="mb-2 flex shrink-0 items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          최근 업로드 영상
          {loading && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
        </h2>
        {/* 음악은 유튜브 단일 — 칩 1개 */}
        <div className="flex flex-wrap gap-2">
          <span className="rounded-full bg-primary px-3 py-1 text-xs font-medium text-primary-foreground">유튜브</span>
        </div>
      </div>

      {videos.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
          아직 업로드된 영상이 없습니다.
        </div>
      ) : (
        <div className="marquee flex min-h-0 flex-1 items-center">
          <div className="marquee__track">
            {[0, 1].map((copy) => videos.map((v) => <VideoCard key={`${v.mix_id}-${copy}`} v={v} />))}
          </div>
          <style jsx>{`
            .marquee {
              overflow: hidden;
            }
            .marquee__track {
              display: flex;
              height: 100%;
              max-height: 330px;
              width: max-content;
              animation: marquee-scroll 15s linear infinite;
            }
            .marquee:hover .marquee__track {
              animation-play-state: paused;
            }
            @keyframes marquee-scroll {
              from {
                transform: translateX(0);
              }
              to {
                transform: translateX(-50%);
              }
            }
            @media (prefers-reduced-motion: reduce) {
              .marquee {
                overflow-x: auto;
              }
              .marquee__track {
                animation: none;
                width: auto;
              }
            }
          `}</style>
        </div>
      )}
    </div>
  )
}
