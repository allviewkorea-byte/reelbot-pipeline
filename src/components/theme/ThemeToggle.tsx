"use client"

import { Moon, Sun } from "lucide-react"
import { applyTheme } from "@/lib/theme"
import { useTheme } from "./useTheme"

/** 사이드바 하단 해/달 아이콘 하나 — 누르면 다크↔화이트, 기기에 저장. */
export function ThemeToggle() {
  const theme = useTheme()
  const light = theme === "light"
  return (
    <button
      type="button"
      onClick={() => applyTheme(light ? "dark" : "light")}
      aria-label={light ? "다크 모드로 전환" : "화이트 모드로 전환"}
      title={light ? "다크 모드로 전환" : "화이트 모드로 전환"}
      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground"
    >
      {light ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
    </button>
  )
}
