"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { Settings, PlayCircle } from "lucide-react"
import { cn } from "@/lib/utils"
import { Separator } from "@/components/ui/separator"
import { HealthIndicator } from "@/components/video/HealthIndicator"

// 사이드바는 채널 DB(useChannels)와 분리한다. 운영 채널은 "백곰의 실화보고서" 1개뿐이고,
// 백곰의 메인 화면은 관제 대시보드(/dashboard)다. 고정 항목 하나만 두고 클릭 시
// /dashboard 로 이동(거기서 "사연 제작 열기" 버튼으로 /sayeon 진입).
// (채널 시스템(useChannels/ChannelProvider/api/channels/lib/supabase, /channels 라우트)은
//  보존 — 여기서 호출만 안 할 뿐. 미래 재도입 대비.)
export function Sidebar() {
  const pathname = usePathname()

  // 백곰 관제 대시보드 = /dashboard(루트 / 도 리다이렉트). 상단 '대시보드' 메뉴와
  // 중복이므로 별도 대시보드 메뉴는 두지 않고 이 항목으로 통합.
  const baekgomActive = pathname === "/dashboard" || pathname === "/"
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
