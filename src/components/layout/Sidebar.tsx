"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  LayoutDashboard,
  Tv2,
  User,
  Wand2,
  Captions,
  TrendingUp,
  LineChart,
  Send,
  History,
  ListChecks,
  DollarSign,
  ScrollText,
  Settings,
  PlayCircle,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { HealthIndicator } from "@/components/video/HealthIndicator"

interface NavItem {
  label: string
  href: string
  icon: React.ComponentType<{ className?: string }>
}

interface NavGroup {
  header?: string
  items: NavItem[]
}

// 영상 제작 흐름순 IA (분석 → 제작 → 발행 → 운영)
const navGroups: NavGroup[] = [
  {
    items: [
      { label: "대시보드", href: "/dashboard", icon: LayoutDashboard },
    ],
  },
  {
    header: "분석",
    items: [
      { label: "트렌드 분석", href: "/trends", icon: LineChart },
      { label: "경쟁사 분석", href: "/competitor", icon: TrendingUp },
    ],
  },
  {
    header: "제작",
    items: [
      { label: "채널", href: "/channels", icon: Tv2 },
      { label: "캐릭터 라이브러리", href: "/character", icon: User },
      { label: "시나리오 보관함", href: "/scenario", icon: Wand2 },
      { label: "자막 스타일", href: "/subtitle-style", icon: Captions },
    ],
  },
  {
    header: "발행",
    items: [
      { label: "멀티 플랫폼 발행", href: "/upload", icon: Send },
      { label: "발행 큐", href: "/publish-queue", icon: ListChecks },
    ],
  },
]

const bottomNavGroup: NavGroup = {
  header: "운영",
  items: [
    { label: "작업 히스토리", href: "/history", icon: History },
    { label: "비용 추적", href: "/costs", icon: DollarSign },
    { label: "로그", href: "/logs", icon: ScrollText },
    { label: "설정", href: "/settings", icon: Settings },
  ],
}

function NavItemLink({ item, pathname }: { item: NavItem; pathname: string }) {
  const isActive =
    pathname === item.href || pathname.startsWith(item.href + "/")

  return (
    <Link
      href={item.href}
      className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150",
        isActive
          ? "bg-primary/20 text-white border border-primary/30"
          : "text-muted-foreground hover:bg-white/5 hover:text-foreground"
      )}
    >
      <item.icon
        className={cn(
          "h-4 w-4 shrink-0",
          isActive ? "text-primary" : "text-muted-foreground"
        )}
      />
      <span>{item.label}</span>
      {isActive && (
        <span className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />
      )}
    </Link>
  )
}

export function Sidebar() {
  const pathname = usePathname()

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

      {/* Main Navigation */}
      <ScrollArea className="flex-1 px-3 py-4">
        <nav className="flex flex-col gap-1">
          {navGroups.map((group, gi) => (
            <div key={group.header ?? `group-${gi}`} className="flex flex-col gap-1">
              {gi > 0 && <Separator className="my-2" />}
              {group.header && (
                <p className="px-3 pb-1 pt-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  {group.header}
                </p>
              )}
              {group.items.map((item) => (
                <NavItemLink key={item.href} item={item} pathname={pathname} />
              ))}
            </div>
          ))}
        </nav>
      </ScrollArea>

      {/* Bottom Navigation */}
      <div className="px-3 pb-4">
        <Separator className="mb-4" />
        {bottomNavGroup.header && (
          <p className="px-3 pb-1 pt-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {bottomNavGroup.header}
          </p>
        )}
        <nav className="flex flex-col gap-1">
          {bottomNavGroup.items.map((item) => (
            <NavItemLink key={item.href} item={item} pathname={pathname} />
          ))}
        </nav>
        <Separator className="my-3" />
        <HealthIndicator />
      </div>
    </aside>
  )
}
