"use client"

import { useSyncExternalStore } from "react"
import { THEME_EVENT, currentTheme, type Theme } from "@/lib/theme"

function subscribe(cb: () => void): () => void {
  window.addEventListener(THEME_EVENT, cb)
  window.addEventListener("storage", cb)
  return () => {
    window.removeEventListener(THEME_EVENT, cb)
    window.removeEventListener("storage", cb)
  }
}

/** 현재 모드(<html data-theme>). 서버 렌더에선 다크. */
export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, currentTheme, () => "dark" as Theme)
}
