"use client"

import { useState } from "react"
import { Film } from "lucide-react"

// UI-3b(다음 PR)에서 이 배열만 유튜브 API 응답으로 갈아끼우면 되도록 타입을 분리.
export type VideoPlatform = "youtube" | "tiktok" | "instagram" | "naverclip"

export interface MarqueeVideo {
  id: string
  platform: VideoPlatform
  title: string
  thumbnailUrl: string // 빈 문자열이면 플레이스홀더 박스(더미)
  viewCount: string
  commentCount: string
  videoUrl: string // 카드 클릭 연결은 UI-3b
}

// 더미 데이터 — 백곰 현황 반영(유튜브 4개). UI-3b 에서 실데이터로 교체.
const DUMMY_VIDEOS: MarqueeVideo[] = [
  { id: "yt-034", platform: "youtube", title: "사연_034 「3년 친구가 내 돈을…」", thumbnailUrl: "", viewCount: "조회 5.1K", commentCount: "댓글 23", videoUrl: "" },
  { id: "yt-033", platform: "youtube", title: "사연_033 「시댁에서 이런 말을…」", thumbnailUrl: "", viewCount: "조회 8.7K", commentCount: "댓글 41", videoUrl: "" },
  { id: "yt-032", platform: "youtube", title: "사연_032 「남친 집에서 발견한…」", thumbnailUrl: "", viewCount: "조회 3.2K", commentCount: "댓글 12", videoUrl: "" },
  { id: "yt-031", platform: "youtube", title: "사연_031 「엄마가 끝까지 숨긴…」", thumbnailUrl: "", viewCount: "조회 12K", commentCount: "댓글 88", videoUrl: "" },
]

const TABS: { id: "all" | VideoPlatform; label: string }[] = [
  { id: "all", label: "전체" },
  { id: "youtube", label: "유튜브" },
  { id: "tiktok", label: "틱톡" },
  { id: "instagram", label: "인스타" },
  { id: "naverclip", label: "네이버클립" },
]

function VideoCard({ v }: { v: MarqueeVideo }) {
  return (
    // 숏폼(세로 9:16) 카드 — B형태: [세로 썸네일] 위 / [텍스트 영역] 아래 분리.
    <div className="mr-3 w-32 shrink-0">
      <div className="flex aspect-[9/16] w-full items-center justify-center overflow-hidden rounded-lg border border-border/60 bg-secondary/50">
        {v.thumbnailUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={v.thumbnailUrl} alt={v.title} className="h-full w-full object-cover" />
        ) : (
          <Film className="h-6 w-6 text-muted-foreground" />
        )}
      </div>
      <div className="mt-2 px-0.5">
        <p className="line-clamp-2 text-xs font-medium leading-snug text-foreground">{v.title}</p>
        <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
          <span>{v.viewCount}</span>
          <span>{v.commentCount}</span>
        </div>
      </div>
    </div>
  )
}

export function RecentVideosMarquee() {
  const [tab, setTab] = useState<"all" | VideoPlatform>("all")
  const videos = tab === "all" ? DUMMY_VIDEOS : DUMMY_VIDEOS.filter((v) => v.platform === tab)

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-foreground">최근 업로드 영상</h2>
        {/* 플랫폼 탭 — 기존 대시보드 탭 스타일/토큰 재사용 */}
        <div className="flex flex-wrap gap-2">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-all ${
                tab === t.id
                  ? "bg-primary text-primary-foreground"
                  : "bg-card border border-border text-muted-foreground hover:text-foreground"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {videos.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
          아직 업로드된 영상이 없습니다.
        </div>
      ) : (
        // 우→좌 무한 마퀴. 카드 세트를 2벌 복제해 -50% 로 끊김 없이 루프.
        // hover 시 일시정지, prefers-reduced-motion 이면 정지 + 가로 스크롤 폴백.
        <div className="marquee">
          <div className="marquee__track">
            {[0, 1].map((copy) =>
              videos.map((v) => <VideoCard key={`${v.id}-${copy}`} v={v} />),
            )}
          </div>
          <style jsx>{`
            .marquee {
              overflow: hidden;
            }
            .marquee__track {
              display: flex;
              width: max-content;
              animation: marquee-scroll 30s linear infinite;
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
