"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { LayoutDashboard, Settings, PlayCircle } from "lucide-react"
import { cn } from "@/lib/utils"
import { Separator } from "@/components/ui/separator"
import { HealthIndicator } from "@/components/video/HealthIndicator"

// 사이드바는 채널 DB(useChannels)와 분리한다. 운영 채널은 "백곰의 실화보고서" 1개뿐이고
// 그 엔진은 /sayeon 이므로, 고정 항목 하나만 두고 클릭 시 /sayeon 으로 직행한다.
// (채널 시스템(useChannels/ChannelProvider/api/channels/lib/supabase, /channels 라우트)은
//  보존 — 여기서 호출만 안 할 뿐. 미래 재도입 대비.)
export function Sidebar() {
  const pathname = usePathname()

  const dashboardActive = pathname === "/dashboard" || pathname === "/"
  // 백곰의 실화보고서 = /sayeon 엔진. 사연 제작 진입(=/sayeon)을 이 항목으로 통합.
  const sayeonActive = pathname === "/sayeon" || pathname.startsWith("/sayeon/")
  const settingsActive =
    pathname === "/settings" || pathname.startsWith("/settings/")

  return (
    <aside className="flex h-screen w-64 shrink-0 flex-col bg-sidebar border-r border-border">
      {/* Logo */}
      <div className="flex h-16 items-center gap-2.5 px-4 border-b border-border">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/20 border border-primary/30">
          <PlayCircle className="h-4 w-4 text-primary" />
        </div>
        <span className="text-base font-semibold tracking-tight text-foreground">
          ReelBot
        </span>
      </div>

      {/* Dashboard */}
      <div className="px-3 pt-4">
        <Link
          href="/dashboard"
          className={cn(
            "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150",
            dashboardActive
              ? "bg-primary/20 text-white border border-primary/30"
              : "text-muted-foreground hover:bg-white/5 hover:text-foreground"
          )}
        >
          <LayoutDashboard
            className={cn(
              "h-4 w-4 shrink-0",
              dashboardActive ? "text-primary" : "text-muted-foreground"
            )}
          />
          <span>대시보드</span>
        </Link>
      </div>

      <div className="px-3 py-2">
        <Separator />
      </div>

      {/* 내 채널 — 채널 DB와 분리한 고정 항목(백곰의 실화보고서 → /sayeon) */}
      <div className="flex min-h-0 flex-1 flex-col px-3">
        <div className="px-3 pb-1">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            내 채널
          </p>
        </div>
        <nav className="flex flex-col gap-1">
          {/* 기존 채널 항목과 동일한 클래스/토큰 재사용. 더미(방콕·도쿄·유럽)는 더 이상 렌더 안 함. */}
          <Link
            href="/sayeon"
            className={cn(
              "flex flex-col gap-1 rounded-lg border px-3 py-2 transition-all duration-150",
              sayeonActive
                ? "border-primary/30 bg-primary/20 text-white"
                : "border-transparent text-muted-foreground hover:bg-white/5 hover:text-foreground"
            )}
          >
            <span className="truncate text-sm font-medium">백곰의 실화보고서</span>
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
              <span className="truncate">유튜브 · 가동 중</span>
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
