"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useState } from "react"
import { Settings, PlayCircle } from "lucide-react"
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

  // 백곰 관제 대시보드 = /dashboard(루트 / 도 리다이렉트). 상단 '대시보드' 메뉴와
  // 중복이므로 별도 대시보드 메뉴는 두지 않고 이 항목으로 통합.
  const baekgomActive = pathname === "/dashboard" || pathname === "/"
  // 음악 채널 = /music (검토 대기 큐) + /music/guide.
  const musicActive = pathname === "/music" || pathname.startsWith("/music/")
  const settingsActive =
    pathname === "/settings" || pathname.startsWith("/settings/")

  return (
    <aside className="flex h-screen w-64 shrink-0 flex-col bg-sidebar border-r border-border">
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

      {/* 내 채널 — 채널 DB와 분리한 고정 항목(백곰의 실화보고서 → 관제 대시보드 /dashboard) */}
      <div className="flex min-h-0 flex-1 flex-col px-3 pt-4">
        <div className="px-3 pb-1">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            내 채널
          </p>
        </div>
        <nav className="flex flex-col gap-1">
          {/* 기존 채널 항목과 동일한 클래스/토큰 재사용. 더미(방콕·도쿄·유럽)는 렌더 안 함. */}
          <Link
            href="/dashboard"
            className={cn(
              "flex flex-col gap-1 rounded-lg border px-3 py-2 transition-all duration-150",
              baekgomActive
                ? "border-primary/30 bg-primary/20 text-white"
                : "border-transparent text-muted-foreground hover:bg-white/5 hover:text-foreground"
            )}
          >
            <span className="truncate text-sm font-medium">백곰의 실화보고서</span>
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              {/* 가동 ON=emerald(맥동) · OFF=불 꺼짐(muted). 가동 상태에 따라 실시간 갱신. */}
              <span
                className={cn(
                  "h-1.5 w-1.5 shrink-0 rounded-full",
                  baekgomLive ? "bg-emerald-500 animate-pulse" : "bg-muted-foreground/40",
                )}
              />
              <span className="truncate">유튜브 · {baekgomLive ? "가동 중" : "대기 중"}</span>
            </span>
          </Link>

          {/* 음악 채널(Revezen) — 검토 대기 큐. 백곰 항목과 동일 클래스/토큰 재사용. */}
          <Link
            href="/music"
            className={cn(
              "flex flex-col gap-1 rounded-lg border px-3 py-2 transition-all duration-150",
              musicActive
                ? "border-primary/30 bg-primary/20 text-white"
                : "border-transparent text-muted-foreground hover:bg-white/5 hover:text-foreground"
            )}
          >
            <span className="truncate text-sm font-medium">{MUSIC_CHANNEL_NAME}</span>
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-500" />
              <span className="truncate">유튜브 · 검토 대기 큐</span>
            </span>
          </Link>
        </nav>
      </div>

      {/* 하단: 설정 + 헬스 인디케이터 */}
      <div className="px-3 pb-4">
        <Separator className="mb-4" />
        <Link
          href="/settings"
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
  )
}
