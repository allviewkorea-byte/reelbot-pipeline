"use client"

import Link from "next/link"
import { usePathname, useSearchParams } from "next/navigation"
import { useEffect, useState, Suspense } from "react"
import { Settings, PlayCircle, Menu, Plus, Activity, UserRound } from "lucide-react"
import { ThemeToggle } from "@/components/theme/ThemeToggle"
import { cn } from "@/lib/utils"
import {
  DEFAULT_MUSIC_CHANNEL,
  MUSIC_CHANNELS,
  WORKOUT_CHANNEL_ID,
  resolveMusicChannel,
  withChannel,
} from "@/lib/music"
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

// 시스템 상태 이상 감지(빨간 배지용). /api/system/status 에서 error/warn 유무.
function useSystemIssue(): boolean {
  const [hasIssue, setHasIssue] = useState(false)
  useEffect(() => {
    let alive = true
    const load = () => {
      fetch("/api/system/status")
        .then((r) => r.json())
        .then((d) => {
          if (!alive) return
          const keys = ["railway", "supabase", "r2", "aws_lambda", "suno", "anthropic", "youtube"]
          setHasIssue(keys.some((k) => d?.[k]?.status === "error"))
        })
        .catch(() => {})
    }
    load()
    const timer = setInterval(load, 60_000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [])
  return hasIssue
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
          ? "border-primary/30 bg-primary/20 text-foreground"
          : "border-transparent text-muted-foreground hover:bg-foreground/5 hover:text-foreground",
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

// useSearchParams 는 Suspense 경계를 요구한다(정적 프리렌더 bail-out 방지).
// fallback 을 빈 값이 아니라 **where 채널 상태**로 렌더해, 정적 HTML 에서도 사이드바가
// 지금과 똑같이 보이고 하이드레이션 후 선택 채널로 바뀐다(레이아웃 시프트 없음).
export function Sidebar() {
  return (
    <Suspense fallback={<SidebarBody activeChannel={DEFAULT_MUSIC_CHANNEL} />}>
      <SidebarWithChannel />
    </Suspense>
  )
}

function SidebarWithChannel() {
  const searchParams = useSearchParams()
  // 선택된 음악 채널 — URL 쿼리가 단일 진실. 미지정·미등록 → where(회귀 0).
  return <SidebarBody activeChannel={resolveMusicChannel(searchParams.get("channel"))} />
}

function SidebarBody({ activeChannel }: { activeChannel: string }) {
  const pathname = usePathname()
  const baekgomLive = useChannelActive(BAEKGOM_CHANNEL_ID)
  // 음악 채널도 같은 channel_status 의 가동 토글(대표 2026-10-28: 검토 대기 대신 가동 중/중단).
  const workoutLive = useChannelActive(WORKOUT_CHANNEL_ID)
  const whereLive = useChannelActive(DEFAULT_MUSIC_CHANNEL)
  const systemIssue = useSystemIssue()
  const [mobileOpen, setMobileOpen] = useState(false)

  // 백곰 관제 대시보드 = /dashboard. 별도 대시보드 메뉴 없이 이 항목으로 통합한다.
  // 루트 "/" 는 시작 화면(운동 채널)으로 즉시 리다이렉트돼 도달하지 않으므로 판정에서 뺐다.
  const baekgomActive = pathname === "/dashboard"
  // 음악 채널 = /music (검토 대기 큐) + /music/guide. 채널은 쿼리로 구분한다.
  const inMusic = pathname === "/music" || pathname.startsWith("/music/")
  const musicActive = inMusic && activeChannel === DEFAULT_MUSIC_CHANNEL
  const workoutActive = inMusic && activeChannel === WORKOUT_CHANNEL_ID
  const instaActive = pathname === "/insta" || pathname.startsWith("/insta/")
  const studioActive = pathname === "/studio" || pathname.startsWith("/studio/")
  const systemActive = pathname === "/system" || pathname.startsWith("/system/")
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

        {/* 내 채널 — 운동 + 백곰 + 음악 + 인스타 쇼핑. 상태 = 가동 중 / 중단(channel_status.is_active). 카드 스타일 통일(데이터·동작 무변경).
            순서는 대표 지시(2주안에몸매만들기 → 백곰 → where). 링크·배지·active 판정은 그대로. */}
        <div className="flex min-h-0 flex-1 flex-col px-3 pt-4">
          <div className="px-3 pb-1">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              내 채널
            </p>
          </div>
          <nav className="flex flex-col gap-1">
            {/* 운동 채널 — 같은 /music 화면을 ?channel= 로 전환한다(2단계). */}
            <ChannelCard
              href={withChannel("/music", WORKOUT_CHANNEL_ID)}
              active={workoutActive}
              icon={MUSIC_CHANNELS[WORKOUT_CHANNEL_ID].icon}
              name={MUSIC_CHANNELS[WORKOUT_CHANNEL_ID].name}
              status={workoutLive ? "live" : "idle"}
              statusText={`유튜브 · ${workoutLive ? "가동 중" : "중단"}`}
              onNavigate={closeMobile}
            />
            <ChannelCard
              href="/dashboard"
              active={baekgomActive}
              icon="🐻"
              name="백곰의 실화보고서"
              status={baekgomLive ? "live" : "idle"}
              statusText={`유튜브 · ${baekgomLive ? "가동 중" : "중단"}`}
              onNavigate={closeMobile}
            />
            <ChannelCard
              href={withChannel("/music", DEFAULT_MUSIC_CHANNEL)}
              active={musicActive}
              icon="🎵"
              name={MUSIC_CHANNEL_NAME}
              status={whereLive ? "live" : "idle"}
              statusText={`유튜브 · ${whereLive ? "가동 중" : "중단"}`}
              onNavigate={closeMobile}
            />
            {/* 인스타 쇼핑(A2-3a) — 착장 만들기 화면. 자동 게시(B단계)·가동 토글 전이라 '중단'. */}
            <ChannelCard
              href="/insta/outfit"
              active={instaActive}
              icon="🛍️"
              name="인스타 쇼핑"
              status="idle"
              statusText="인스타 · 중단"
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

        {/* 하단: 시스템 상태 + 설정 + 헬스 인디케이터 */}
        <div className="px-3 pb-4">
          <Separator className="mb-4" />
          {/* 캐릭터 스튜디오(채널 공통) — 캐릭터 기준 이미지 등록·확정 */}
          <Link
            href="/studio"
            onClick={closeMobile}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150",
              studioActive
                ? "bg-primary/20 text-foreground border border-primary/30"
                : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground"
            )}
          >
            <UserRound
              className={cn(
                "h-4 w-4 shrink-0",
                studioActive ? "text-primary" : "text-muted-foreground"
              )}
            />
            <span>캐릭터 스튜디오</span>
          </Link>
          <Link
            href="/system"
            onClick={closeMobile}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150",
              systemActive
                ? "bg-primary/20 text-foreground border border-primary/30"
                : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground"
            )}
          >
            <Activity
              className={cn(
                "h-4 w-4 shrink-0",
                systemActive ? "text-primary" : "text-muted-foreground"
              )}
            />
            <span>시스템 상태</span>
            {systemIssue && (
              <span className="ml-auto h-2 w-2 shrink-0 rounded-full bg-red-500" />
            )}
          </Link>
          <div className="flex items-center gap-1">
          <Link
            href="/settings"
            onClick={closeMobile}
            className={cn(
              "flex flex-1 items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150",
              settingsActive
                ? "bg-primary/20 text-foreground border border-primary/30"
                : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground"
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
          {/* 다크/화이트 전환(해/달) — 앱 전체 공통, 기기에 저장 */}
          <ThemeToggle />
          </div>
          <Separator className="my-3" />
          <HealthIndicator />
        </div>
      </aside>
    </>
  )
}
