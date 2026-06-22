"use client"

import { useEffect, useState } from "react"
import { Film, Loader2 } from "lucide-react"

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

// 네이버클립 탭 제거 — 노드그래프 분기(유튜브·틱톡·인스타)와 일관. 네이버는 어디에도 안 보임.
const TABS: { id: "all" | VideoPlatform; label: string }[] = [
  { id: "all", label: "전체" },
  { id: "youtube", label: "유튜브" },
  { id: "tiktok", label: "틱톡" },
  { id: "instagram", label: "인스타" },
]

function VideoCard({ v }: { v: MarqueeVideo }) {
  return (
    // 숏폼(세로 9:16) 카드 — B형태: [세로 썸네일] 위 / [텍스트 영역] 아래 분리.
    // 높이 주도: 카드 높이(h-full)는 그대로. 썸네일 높이를 '확정값'으로 만든 뒤
    // aspect-[9/16]로 폭을 파생 → 카드 폭 = 썸네일 높이 × 9/16 (진짜 세로 9:16).
    //
    // 이전(#108) 실패 원인: 썸네일 높이를 flex-1 로 뒀다. flex 메인축(세로) 크기는
    // '레이아웃 단계'에서 정해지는데, 트랙의 width:max-content 가 카드 '폭'을 계산하는
    // 시점엔 아직 높이가 미정 → aspect 가 높이→폭 변환을 못 해 폭이 9:16으로 안 묶였다.
    // (w-0 min-w-full 은 '텍스트'만 0 기여로 만들 뿐, 썸네일 높이 미정 문제는 못 고침.)
    //
    // 해결: 썸네일 높이를 h-[calc(100%-4.5rem)] (=확정된 카드 높이 기반)로 고정 →
    // aspect 가 폭을 확정. items-center 로 stretch(폭 강제 늘림)도 차단,
    // 텍스트는 w-0 min-w-full 로 폭 계산에 0 기여 → 카드 폭 = 썸네일 폭.
    <div className="mr-4 flex h-full shrink-0 flex-col items-center">
      <div className="flex aspect-[9/16] h-[calc(100%_-_4.5rem)] w-auto items-center justify-center overflow-hidden rounded-lg border border-border/60 bg-secondary/50">
        {v.thumbnailUrl ? (
          // 16:9 원본을 9:16 영역에 크롭 채움(왜곡 없음).
          // eslint-disable-next-line @next/next/no-img-element
          <img src={v.thumbnailUrl} alt={v.title} className="h-full w-full object-cover" />
        ) : (
          <Film className="h-10 w-10 text-muted-foreground" />
        )}
      </div>
      <div className="mt-2 h-16 w-0 min-w-full shrink-0 overflow-hidden px-0.5">
        <p className="line-clamp-2 text-sm font-medium leading-snug text-foreground">{v.title}</p>
        <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
          <span>{v.viewCount}</span>
          <span>{v.commentCount}</span>
        </div>
      </div>
    </div>
  )
}

export function RecentVideosMarquee() {
  const [tab, setTab] = useState<"all" | VideoPlatform>("all")
  // 초기엔 더미로 첫 페인트(화면 안 빔) → /api/channel-videos 실데이터 도착 시 교체.
  // 공개 영상 0개/실패면 더미 유지(폴백). setState 는 비동기 콜백에서만 호출(effect 본문 직접 호출 회피).
  const [source, setSource] = useState<MarqueeVideo[]>(DUMMY_VIDEOS)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    fetch("/api/channel-videos")
      .then((r) => r.json())
      .then((d) => {
        if (!active) return
        const list = Array.isArray(d?.videos) ? (d.videos as MarqueeVideo[]) : []
        if (list.length > 0) setSource(list) // 공개 영상 있으면 교체, 없으면 더미 유지
      })
      .catch(() => {
        /* 실패 → 더미 유지 */
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  const videos = tab === "all" ? source : source.filter((v) => v.platform === tab)

  return (
    <div className="flex min-h-[300px] flex-1 flex-col rounded-xl border border-border bg-card p-3 md:min-h-0">
      <div className="mb-2 flex shrink-0 items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          최근 업로드 영상
          {loading && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
        </h2>
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
        // 카드는 행 높이 주도지만 max-height(상한)로 과확대 방지(선명도↑) + 세로 중앙 정렬.
        <div className="marquee flex min-h-0 flex-1 items-center">
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
              height: 100%;
              max-height: 330px;
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
