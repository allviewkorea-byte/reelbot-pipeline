"use client"

import { useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  LayoutDashboard,
  Settings,
  PlayCircle,
  Plus,
  ChevronRight,
  Clapperboard,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Separator } from "@/components/ui/separator"
import { HealthIndicator } from "@/components/video/HealthIndicator"
import { useChannels } from "@/components/channels/ChannelProvider"
import { PLATFORM_LABELS, type Channel } from "@/lib/channels"

// 가동 중(활성) 판정 — 기존 statusVariant 필드만 사용 (스키마 변경 없음).
// active/growing = 활성, pending = 미사용·보관.
function isRunning(ch: Channel): boolean {
  return ch.statusVariant === "active" || ch.statusVariant === "growing"
}

function ChannelNavItem({ ch, active }: { ch: Channel; active: boolean }) {
  const running = isRunning(ch)
  return (
    <Link
      href={`/channels/${ch.id}`}
      className={cn(
        "flex flex-col gap-1 rounded-lg border px-3 py-2 transition-all duration-150",
        active
          ? "border-primary/30 bg-primary/20 text-white"
          : "border-transparent text-muted-foreground hover:bg-white/5 hover:text-foreground"
      )}
    >
      <span className="truncate text-sm font-medium">{ch.name}</span>
      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <span
          className={cn(
            "h-1.5 w-1.5 shrink-0 rounded-full",
            running ? "bg-emerald-500" : "bg-muted-foreground/40"
          )}
        />
        <span className="truncate">
          {PLATFORM_LABELS[ch.platform]} · {ch.status}
        </span>
      </span>
    </Link>
  )
}

export function Sidebar() {
  const pathname = usePathname()
  const { channels } = useChannels()
  const [archiveOpen, setArchiveOpen] = useState(false)

  const activeChannels = channels.filter(isRunning)
  const archivedChannels = channels.filter((c) => !isRunning(c))

  const dashboardActive = pathname === "/dashboard" || pathname === "/"
  // 사연 제작 — 릴봇 핵심 기능(/sayeon). 사이드바 상시 노출.
  const sayeonActive = pathname === "/sayeon" || pathname.startsWith("/sayeon/")
  const settingsActive =
    pathname === "/settings" || pathname.startsWith("/settings/")
  const isChannelActive = (id: string) => pathname === `/channels/${id}`

  // 기본은 접힘. 단 현재 보고 있는 채널이 보관 그룹이면 활성 표시가 보이도록 펼친다.
  const activeIsArchived = archivedChannels.some((c) => isChannelActive(c.id))
  const archiveExpanded = archiveOpen || activeIsArchived

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

        {/* 사연 제작 — 릴봇 핵심 기능. 절대 삭제 불가. */}
        <Link
          href="/sayeon"
          className={cn(
            "mt-1 flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150",
            sayeonActive
              ? "bg-primary/20 text-white border border-primary/30"
              : "text-muted-foreground hover:bg-white/5 hover:text-foreground"
          )}
        >
          <Clapperboard
            className={cn(
              "h-4 w-4 shrink-0",
              sayeonActive ? "text-primary" : "text-muted-foreground"
            )}
          />
          <span>사연 제작</span>
        </Link>
      </div>

      <div className="px-3 py-2">
        <Separator />
      </div>

      {/* 내 채널 — 남은 공간을 채우고 목록 영역만 내부 스크롤 */}
      <div className="flex min-h-0 flex-1 flex-col px-3">
        <div className="flex items-center justify-between px-3 pb-1">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            내 채널
          </p>
          <Link
            href="/channels"
            className="flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            <Plus className="h-3.5 w-3.5" />
            새 채널
          </Link>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {channels.length === 0 ? (
            <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border px-3 py-6 text-center">
              <p className="text-xs text-muted-foreground">아직 채널이 없습니다</p>
              <Link
                href="/channels"
                className="flex items-center gap-1 text-xs font-medium text-primary hover:underline"
              >
                <Plus className="h-3.5 w-3.5" />
                새 채널
              </Link>
            </div>
          ) : (
            <nav className="flex flex-col gap-1 pb-2">
              {/* 활성 채널 */}
              {activeChannels.length > 0 && (
                <>
                  <p className="px-3 pb-1 pt-1 text-xs font-medium text-muted-foreground/70">
                    활성 채널
                  </p>
                  {activeChannels.map((ch) => (
                    <ChannelNavItem
                      key={ch.id}
                      ch={ch}
                      active={isChannelActive(ch.id)}
                    />
                  ))}
                </>
              )}

              {/* 미사용·보관 (접기 가능, 기본 접힘) */}
              {archivedChannels.length > 0 && (
                <div className="mt-1">
                  <button
                    type="button"
                    onClick={() => setArchiveOpen((v) => !v)}
                    className="flex w-full items-center gap-1.5 px-3 py-1 text-xs font-medium text-muted-foreground/70 transition-colors hover:text-foreground"
                  >
                    <ChevronRight
                      className={cn(
                        "h-3 w-3 shrink-0 transition-transform",
                        archiveExpanded && "rotate-90"
                      )}
                    />
                    <span>미사용·보관</span>
                    <span className="ml-1 text-muted-foreground/50">
                      {archivedChannels.length}
                    </span>
                  </button>
                  {archiveExpanded && (
                    <div className="flex flex-col gap-1 pt-1">
                      {archivedChannels.map((ch) => (
                        <ChannelNavItem
                          key={ch.id}
                          ch={ch}
                          active={isChannelActive(ch.id)}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </nav>
          )}
        </div>
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
