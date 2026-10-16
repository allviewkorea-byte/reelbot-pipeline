// 다크/화이트 모드(앱 전체 공통). 기본 다크 — 화이트는 <html data-theme="light"> 일 때만.
// 저장은 브라우저 localStorage(기기별). 첫 화면 깜빡임 방지는 layout.tsx <head> 인라인 스크립트
// (THEME_INIT_SCRIPT)가 그리기 전에 data-theme 을 붙여서 한다.

export type Theme = "dark" | "light"

export const THEME_STORAGE_KEY = "reelbot-theme"
export const THEME_EVENT = "reelbot:theme-changed"

// 휴대폰 주소창 색(meta theme-color) — 각 모드 --background 값의 hex(신규 토큰 아님).
export const THEME_COLOR: Record<Theme, string> = { dark: "#0f1729", light: "#f6f7f9" }

export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_STORAGE_KEY}");if(t==="light"){document.documentElement.setAttribute("data-theme","light");var m=document.querySelector('meta[name="theme-color"]');if(m)m.setAttribute("content","${THEME_COLOR.light}")}}catch(e){}})();`

export function currentTheme(): Theme {
  if (typeof document === "undefined") return "dark"
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark"
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  if (theme === "light") root.setAttribute("data-theme", "light")
  else root.removeAttribute("data-theme")
  document.querySelectorAll('meta[name="theme-color"]').forEach((m) => m.setAttribute("content", THEME_COLOR[theme]))
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    /* 저장 불가(사생활 모드 등) — 이번 화면에만 적용 */
  }
  window.dispatchEvent(new CustomEvent<Theme>(THEME_EVENT, { detail: theme }))
}
