"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useState } from "react"
import { Settings, PlayCircle, Menu, Plus } from "lucide-react"
import { cn } from "@/lib/utils"
import { Separator } from "@/components/ui/separator"
import { HealthIndicator } from "@/components/video/HealthIndicator"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"
import { CHANNEL_STATUS_EVENT, type ChannelStatusDetail } from "@/lib/channel-status"

// 채널별 가동 상태를 읽어 사이드바에 색으로 표시한다. 지금은 백곰 1개라 1개만 폴링하지만,
// channelId 키로 받으므로 미래 다채널이면 채널 목록을 map 돌려 각각 호출하면 된다.
function useChannelActive(channelId: string): boolean {
  const [active, setActive] = useState(false)
  useEffect(() => {
    let alive = true
    const load = () => {
      fetch(`/api/channel-status?channelId=${channelId}`)
        .then((r) => r.json())
        .then((d) => {
          if (alive) setActive(Boolean(d?.isActive))
        })
        .catch(() => {
          /* 실패 → 기존 상태 유지 */
        })
    }
    load()
    // 다른 화면 보다가도 반영되게 주기 폴링 + 탭 포커스 복귀 시 갱신.
    const timer = setInterval(load, 12000)
    const onFocus = () => load()
    // 같은 탭에서 토글하면 폴링 기다리지 않고 즉시 반영.
    const onEvt = (e: Event) => {
      const detail = (e as CustomEvent<ChannelStatusDetail>).detail
      if (detail && detail.channelId === channelId) setActive(Boolean(detail.isActive))
      else load()
    }
    window.addEventListener("focus", onFocus)
    window.addEventListener(CHANNEL_STATUS_EVENT, onEvt)
    return () => {
      alive = false
      clearInterval(timer)
      window.removeEventListener("focus", onFocus)
      window.removeEventListener(CHANNEL_STATUS_EVENT, onEvt)
    }
  }, [channelId])
  return active
}

// 음악 채널 검토 대기 수(주황 배지). /api/music/queue 길이.
function useMusicQueueCount(): number {
  const [count, setCount] = useState(0)
  useEffect(() => {
    let alive = true
    const load = () => {
      fetch("/api/music/queue")
        .then((r) => r.json())
        .then((d) => {
          if (alive) setCount(Array.isArray(d?.queue) ? d.queue.length : 0)
        })
        .catch(() => {
          /* 실패 → 기존 값 유지 */
        })
    }
    load()
    const timer = setInterval(load, 20000)
    const onFocus = () => load()
    window.addEventListener("focus", onFocus)
    return () => {
      alive = false
      clearInterval(timer)
      window.removeEventListener("focus", onFocus)
    }
  }, [])
  return count
}

type DotStatus = "live" | "idle" | "error"

// 채널 카드(백곰·음악 공통). 아이콘 + 채널명 + 상태점·텍스트 + 조건부 이슈 배지.
function ChannelCard({
  href,
  active,
  icon,
  name,
  status,
  statusText,
  badge,
  onNavigate,
}: {
  href: string
  active: boolean
  icon: string
  name: string
  status: DotStatus
  statusText: string
  badge?: { label: string; tone: "review" | "error" }
  onNavigate?: () => void
}) {
  const dot =
    status === "live"
      ? "bg-emerald-500 animate-pulse"
      : status === "error"
        ? "bg-red-500"
        : "bg-muted-foreground/40"
  return (
    <Link
      href={href}
      onClick={onNavigate}
      className={cn(
        "flex items-center gap-3 rounded-lg border px-3 py-2.5 transition-all duration-150",
        active
          ? "border-primary/30 bg-primary/20 text-white"
          : "border-transparent text-muted-foreground hover:bg-white/5 hover:text-foreground",
      )}
    >
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-secondary/40 text-base">
        {icon}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="truncate text-sm font-medium">{name}</span>
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dot)} />
          <span className="truncate">{statusText}</span>
        </span>
      </div>
      {badge && (
        <span
          className={cn(
            "shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium",
            badge.tone === "error"
              ? "bg-red-500/15 text-red-400"
              : "bg-amber-500/15 text-amber-400",
          )}
        >
          {badge.label}
        </span>
      )}
    </Link>
  )
}

// 사이드바는 채널 DB(useChannels)와 분리한다. 운영 채널은 "백곰의 실화보고서" 1개뿐이고,
// 백곰의 메인 화면은 관제 대시보드(/dashboard)다. 고정 항목 하나만 두고 클릭 시
// /dashboard 로 이동(거기서 "사연 제작 열기" 버튼으로 /sayeon 진입).
// (채널 시스템(useChannels/ChannelProvider/api/channels/lib/supabase, /channels 라우트)은
//  보존 — 여기서 호출만 안 할 뿐. 미래 재도입 대비.)
// 음악 채널명(비밀 아님 → NEXT_PUBLIC 허용). 기본 "음악 채널".
const MUSIC_CHANNEL_NAME = process.env.NEXT_PUBLIC_MUSIC_CHANNEL_NAME || "음악 채널"

export function Sidebar() {
  const pathname = usePathname()
  const baekgomLive = useChannelActive(BAEKGOM_CHANNEL_ID)
  const musicQueue = useMusicQueueCount()
  const [mobileOpen, setMobileOpen] = useState(false)

  // 백곰 관제 대시보드 = /dashboard(루트 / 도 리다이렉트). 상단 '대시보드' 메뉴와
  // 중복이므로 별도 대시보드 메뉴는 두지 않고 이 항목으로 통합.
  const baekgomActive = pathname === "/dashboard" || pathname === "/"
  // 음악 채널 = /music (검토 대기 큐) + /music/guide.
  const musicActive = pathname === "/music" || pathname.startsWith("/music/")
  const settingsActive =
    pathname === "/settings" || pathname.startsWith("/settings/")

  const closeMobile = () => setMobileOpen(false)

  return (
    <>
      {/* 모바일 햄버거(데스크탑 숨김). 사이드바를 드로어로 토글 — 레이아웃/백곰 데스크탑 무영향. */}
      <button
        type="button"
        onClick={() => setMobileOpen(true)}
        aria-label="메뉴 열기"
        className="fixed left-3 top-3 z-30 flex h-10 w-10 items-center justify-center rounded-lg border border-border bg-card text-foreground md:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>
      {/* 모바일 백드롭 */}
      {mobileOpen && (
        <div
          onClick={closeMobile}
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          aria-hidden="true"
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex h-screen w-64 shrink-0 flex-col border-r border-border bg-sidebar transition-transform md:static md:z-auto md:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        )}
      >
        {/* Logo — 클릭 시 현재 화면 새로고침(캐스트 등 클라이언트 데이터 재조회) */}
        <div className="flex h-16 items-center px-4 border-b border-border">
          <button
            type="button"
            onClick={() => window.location.reload()}
            title="새로고침"
            className="flex items-center gap-2.5"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/20 border border-primary/30">
              <PlayCircle className="h-4 w-4 text-primary" />
            </div>
            <span className="text-base font-semibold tracking-tight text-foreground">
              ReelBot
            </span>
          </button>
        </div>

        {/* 내 채널 — 백곰 + 음악(검토 대기 큐). 카드 스타일 통일(데이터·동작 무변경). */}
        <div className="flex min-h-0 flex-1 flex-col px-3 pt-4">
          <div className="px-3 pb-1">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              내 채널
            </p>
          </div>
          <nav className="flex flex-col gap-1">
            <ChannelCard
              href="/dashboard"
              active={baekgomActive}
              icon="🐻"
              name="백곰의 실화보고서"
              status={baekgomLive ? "live" : "idle"}
              statusText={`유튜브 · ${baekgomLive ? "가동 중" : "대기 중"}`}
              onNavigate={closeMobile}
            />
            <ChannelCard
              href="/music"
              active={musicActive}
              icon="🎵"
              name={MUSIC_CHANNEL_NAME}
              status="idle"
              statusText="유튜브 · 검토 대기"
              badge={musicQueue > 0 ? { label: `검토 ${musicQueue}`, tone: "review" } : undefined}
              onNavigate={closeMobile}
            />

            {/* 채널 추가(placeholder — 동작은 후속) */}
            <button
              type="button"
              disabled
              title="채널 추가(준비 중)"
              className="mt-1 flex cursor-not-allowed items-center gap-3 rounded-lg border border-dashed border-border px-3 py-2.5 text-muted-foreground/60"
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-dashed border-border">
                <Plus className="h-4 w-4" />
              </div>
              <span className="text-sm font-medium">채널 추가</span>
            </button>
          </nav>
        </div>

        {/* 하단: 설정 + 헬스 인디케이터 */}
        <div className="px-3 pb-4">
          <Separator className="mb-4" />
          <Link
            href="/settings"
            onClick={closeMobile}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150",
              settingsActive
                ? "bg-primary/20 text-white border border-primary/30"
                : "text-muted-foreground hover:bg-white/5 hover:text-foreground"
            )}
          >
            <Settings
              className={cn(
                "h-4 w-4 shrink-0",
                settingsActive ? "text-primary" : "text-muted-foreground"
              )}
            />
            <span>설정</span>
          </Link>
          <Separator className="my-3" />
          <HealthIndicator />
        </div>
      </aside>
    </>
  )
}
