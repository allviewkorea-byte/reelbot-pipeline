"use client"

import { useEffect, useState } from "react"

// 섹션 접기/펼치기 — 모바일 스크롤 줄이기용. 선택은 이 브라우저에만 기억(실패해도 기본값으로 동작).
export function useFold(key: string, defaultOpen: boolean) {
  const [open, setOpen] = useState(defaultOpen)
  useEffect(() => {
    try {
      const v = localStorage.getItem(`fold:${key}`)
      // 서버 렌더와 맞추려고 마운트 후에 기억값을 반영
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (v !== null) setOpen(v === "1")
    } catch {}
  }, [key])
  const toggle = () =>
    setOpen((o) => {
      try {
        localStorage.setItem(`fold:${key}`, o ? "0" : "1")
      } catch {}
      return !o
    })
  return [open, toggle] as const
}
