"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  LayoutDashboard,
  User,
  Tv2,
  TrendingUp,
  Upload,
  Wand2,
  Clapperboard,
  MapPin,
  Layers,
  SlidersHorizontal,
  Zap,
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

const mainNavItems: NavItem[] = [
  { label: "대시보드",    href: "/dashboard",   icon: LayoutDashboard },
  { label: "캐릭터 설정", href: "/character",   icon: User },
  { label: "채널 관리",   href: "/channels",    icon: Tv2 },
  { label: "경쟁사 분석", href: "/competitor",  icon: TrendingUp },
  { label: "멀티 업로드", href: "/upload",      icon: Upload },
  { label: "시나리오 생성",href: "/scenario",   icon: Wand2 },
  { label: "영상 제작",   href: "/video",       icon: Clapperboard },
  { label: "실제 공간",   href: "/space",       icon: MapPin },
  { label: "Adobe 편집",  href: "/adobe",       icon: Layers },
  { label: "모드 설정",   href: "/mode",        icon: SlidersHorizontal },
  { label: "자동화",      href: "/automation",  icon: Zap },
]

const bottomNavItems: NavItem[] = [
  { label: "비용 추적", href: "/costs",    icon: DollarSign },
  { label: "로그",      href: "/logs",     icon: ScrollText },
  { label: "설정",      href: "/settings", icon: Settings },
]

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
          {mainNavItems.map((item) => (
            <NavItemLink key={item.href} item={item} pathname={pathname} />
          ))}
        </nav>
      </ScrollArea>

      {/* Bottom Navigation */}
      <div className="px-3 pb-4">
        <Separator className="mb-4" />
        <nav className="flex flex-col gap-1">
          {bottomNavItems.map((item) => (
            <NavItemLink key={item.href} item={item} pathname={pathname} />
          ))}
        </nav>
        <Separator className="my-3" />
        <HealthIndicator />
      </div>
    </aside>
  )
}
