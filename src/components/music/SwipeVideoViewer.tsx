"use client"

// PiP + 스와이프 전체화면 영상 뷰어 — 검토 대기 카드와 분리된 별도 레이어(fixed overlay).
// 좌우 스와이프/화살표로 목록 순서대로 이전·다음 영상 탐색, PiP 버튼으로 백그라운드 재생.
// 기존 카드 UI 는 건드리지 않고, queue 페이지가 이 뷰어를 조건부로 띄운다.

import { useCallback, useEffect, useRef, useState, type TouchEvent as ReactTouchEvent } from "react"
import { X, ChevronLeft, ChevronRight, PictureInPicture2 } from "lucide-react"
import type { QueueItem } from "@/components/music/MusicQueueCard"
import { isPipSupported, togglePip } from "@/lib/pip"

const SWIPE_THRESHOLD = 50 // px — 이 이상 가로로 끌어야 전환

export function SwipeVideoViewer({
  items,
  index,
  onIndexChange,
  onClose,
}: {
  items: QueueItem[]
  index: number
  onIndexChange: (next: number) => void
  onClose: () => void
}) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const touchStartX = useRef<number | null>(null)
  const touchStartY = useRef<number | null>(null)
  const [pipActive, setPipActive] = useState(false)
  const [pipOk, setPipOk] = useState(false)

  const current = items[index]
  const hasPrev = index > 0
  const hasNext = index < items.length - 1

  const goPrev = useCallback(() => {
    if (index > 0) onIndexChange(index - 1)
  }, [index, onIndexChange])
  const goNext = useCallback(() => {
    if (index < items.length - 1) onIndexChange(index + 1)
  }, [index, items.length, onIndexChange])

  // 키보드 — ←/→ 전환, Esc 닫기(데스크탑 편의).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") goPrev()
      else if (e.key === "ArrowRight") goNext()
      else if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [goPrev, goNext, onClose])

  // 영상이 바뀌면(스와이프/화살표) 이전 영상을 멈추고 새 영상을 자동 재생.
  // src 가 바뀐 직후 load → play. PiP 중이면 브라우저가 PiP 창을 새 영상으로 유지.
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    v.play().catch(() => {
      /* 자동재생 차단(사용자 제스처 필요) → 무시, 컨트롤로 재생 가능 */
    })
  }, [index])

  // PiP 지원 감지 — video 엘리먼트 마운트 후 확인(표준 + iOS webkit).
  useEffect(() => {
    setPipOk(isPipSupported(videoRef.current))
  }, [index])

  // PiP 상태 추적 — 시스템 PiP 창을 닫아도 버튼 상태가 맞도록.
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    const onEnter = () => setPipActive(true)
    const onLeave = () => setPipActive(false)
    v.addEventListener("enterpictureinpicture", onEnter)
    v.addEventListener("leavepictureinpicture", onLeave)
    return () => {
      v.removeEventListener("enterpictureinpicture", onEnter)
      v.removeEventListener("leavepictureinpicture", onLeave)
    }
  }, [])

  const handleTogglePip = useCallback(async () => {
    const v = videoRef.current
    if (v) await togglePip(v)
  }, [])

  const onTouchStart = (e: ReactTouchEvent) => {
    touchStartX.current = e.touches[0].clientX
    touchStartY.current = e.touches[0].clientY
  }
  const onTouchEnd = (e: ReactTouchEvent) => {
    if (touchStartX.current == null || touchStartY.current == null) return
    const dx = touchStartX.current - e.changedTouches[0].clientX
    const dy = touchStartY.current - e.changedTouches[0].clientY
    touchStartX.current = null
    touchStartY.current = null
    // 가로 이동이 세로보다 우세할 때만 전환(세로 스크롤·컨트롤 조작과 충돌 방지).
    if (Math.abs(dx) > SWIPE_THRESHOLD && Math.abs(dx) > Math.abs(dy)) {
      if (dx > 0) goNext()
      else goPrev()
    }
  }

  if (!current) return null

  return (
    <div className="fixed inset-0 z-[60] flex flex-col bg-black/95 backdrop-blur-sm">
      {/* 상단 바 — 번호 + 닫기 */}
      <div className="flex items-center justify-between px-4 py-3 text-white">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={goPrev}
            disabled={!hasPrev}
            aria-label="이전 영상"
            className="flex h-9 w-9 items-center justify-center rounded-full bg-white/10 transition hover:bg-white/20 disabled:opacity-30"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          <span className="min-w-[56px] text-center text-sm font-medium tabular-nums">
            {index + 1} / {items.length}
          </span>
          <button
            type="button"
            onClick={goNext}
            disabled={!hasNext}
            aria-label="다음 영상"
            className="flex h-9 w-9 items-center justify-center rounded-full bg-white/10 transition hover:bg-white/20 disabled:opacity-30"
          >
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="닫기"
          className="flex h-9 w-9 items-center justify-center rounded-full bg-white/10 transition hover:bg-white/20"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* 영상 영역 — 스와이프 감지. 좌우 화살표(데스크탑 호버) 오버레이. */}
      <div
        className="relative flex flex-1 items-center justify-center overflow-hidden px-2"
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
      >
        {hasPrev && (
          <button
            type="button"
            onClick={goPrev}
            aria-label="이전 영상"
            className="absolute left-2 z-10 hidden h-11 w-11 items-center justify-center rounded-full bg-black/40 text-white transition hover:bg-black/60 md:flex"
          >
            <ChevronLeft className="h-6 w-6" />
          </button>
        )}
        <video
          // key 로 src 교체 시 엘리먼트를 재생성 → 이전 영상 상태가 새 영상에 새지 않음.
          key={current.mix_id}
          ref={videoRef}
          src={current.mp4_url}
          controls
          autoPlay
          playsInline
          preload="metadata"
          className="max-h-full max-w-full"
        />
        {hasNext && (
          <button
            type="button"
            onClick={goNext}
            aria-label="다음 영상"
            className="absolute right-2 z-10 hidden h-11 w-11 items-center justify-center rounded-full bg-black/40 text-white transition hover:bg-black/60 md:flex"
          >
            <ChevronRight className="h-6 w-6" />
          </button>
        )}
      </div>

      {/* 하단 — 제목 + PiP. 컨트롤(재생/볼륨)은 video 기본 controls 사용. */}
      <div className="flex items-center justify-between gap-3 px-4 py-3 text-white">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">
            {current.title_kr || current.slug}
          </p>
          <p className="truncate text-xs text-white/60">
            {[current.genre, current.mood].filter(Boolean).join(" · ")}
          </p>
        </div>
        {pipOk && (
          <button
            type="button"
            onClick={handleTogglePip}
            aria-label="PiP(작은 화면) 전환"
            title="다른 앱을 봐도 작은 창으로 계속 재생"
            className={`flex h-10 shrink-0 items-center gap-1.5 rounded-full px-3 text-xs font-medium transition ${
              pipActive ? "bg-primary text-primary-foreground" : "bg-white/10 hover:bg-white/20"
            }`}
          >
            <PictureInPicture2 className="h-4 w-4" /> PiP
          </button>
        )}
      </div>
    </div>
  )
}
