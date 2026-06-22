"use client"

// 최근 업로드 음악 영상 가로 마퀴 — 백곰 RecentVideosMarquee 패턴 차용(직접 import 금지).
// styled-jsx 로 끊김없는 스크롤(목록 2배 복제), hover 정지, reduced-motion 시 가로 스크롤 폴백.
import { useEffect, useState } from "react"
import { Music, Play } from "lucide-react"

interface RecentVideo {
  mix_id: string
  title_kr?: string
  genre?: string
  youtube_url?: string
  thumbnail_url?: string | null
}

export function MusicMarquee() {
  const [videos, setVideos] = useState<RecentVideo[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    fetch("/api/music/recent")
      .then((r) => r.json())
      .then((d) => setVideos(Array.isArray(d?.videos) ? d.videos : []))
      .catch(() => setVideos([]))
      .finally(() => setLoaded(true))
  }, [])

  if (loaded && videos.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border/60 px-4 py-6 text-center text-sm text-muted-foreground">
        아직 공개 업로드된 영상이 없습니다.
      </div>
    )
  }

  const loop = videos.length > 0 ? [...videos, ...videos] : []

  return (
    <div className="m-marquee group relative overflow-hidden">
      <div className="m-marquee-track flex gap-3">
        {loop.map((v, i) => (
          <a
            key={`${v.mix_id}-${i}`}
            href={v.youtube_url || "#"}
            target={v.youtube_url ? "_blank" : undefined}
            rel="noreferrer"
            className="group/item relative flex aspect-video w-44 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border bg-secondary/30"
            title={v.title_kr || ""}
          >
            {v.thumbnail_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={v.thumbnail_url} alt={v.title_kr || ""} className="h-full w-full object-cover" />
            ) : (
              <Music className="h-6 w-6 text-muted-foreground" />
            )}
            <span className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity group-hover/item:opacity-100">
              <Play className="h-6 w-6 text-white" />
            </span>
            <span className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/70 to-transparent px-2 py-1 text-[11px] text-white">
              {v.title_kr}
            </span>
          </a>
        ))}
      </div>
      <style jsx>{`
        .m-marquee-track {
          width: max-content;
          animation: m-scroll 28s linear infinite;
        }
        .m-marquee:hover .m-marquee-track {
          animation-play-state: paused;
        }
        @keyframes m-scroll {
          from {
            transform: translateX(0);
          }
          to {
            transform: translateX(-50%);
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .m-marquee {
            overflow-x: auto;
          }
          .m-marquee-track {
            animation: none;
          }
        }
      `}</style>
    </div>
  )
}
