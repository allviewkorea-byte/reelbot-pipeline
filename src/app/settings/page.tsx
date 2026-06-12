"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

// 백엔드 절대 URL — OAuth 는 풀페이지 리다이렉트(구글→백엔드 콜백)라 프록시 불가.
const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(/\/$/, "")

export default function SettingsPage() {
  const [connected, setConnected] = useState<boolean | null>(null)
  const [justConnected, setJustConnected] = useState(false)

  useEffect(() => {
    // 콜백 리다이렉트(?youtube=connected) 감지 + 연동 상태 조회(Next 프록시 경유).
    // setState 는 비동기 콜백 안에서만 호출(effect 본문 직접 호출 회피).
    const justConn =
      new URLSearchParams(window.location.search).get("youtube") === "connected"
    fetch("/api/youtube-status")
      .then((r) => r.json())
      .then((d) => {
        setConnected(Boolean(d?.connected))
        if (justConn) setJustConnected(true)
      })
      .catch(() => {
        setConnected(false)
        if (justConn) setJustConnected(true)
      })
  }, [])

  const authHref = API_BASE ? `${API_BASE}/api/youtube/auth` : "#"

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">설정</h1>
        <p className="text-sm text-muted-foreground mt-1">외부 채널 연동 및 게시 설정</p>
      </div>

      <div className="rounded-lg border border-border bg-card p-5 max-w-xl space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-medium text-foreground">유튜브 연동</h2>
            <p className="text-sm text-muted-foreground mt-1">
              연동하면 완성된 사연 영상을 유튜브 채널에 자동 업로드할 수 있어요.
            </p>
          </div>
          {connected === null ? (
            <Badge variant="secondary">확인 중…</Badge>
          ) : connected ? (
            <Badge>연동됨 ✅</Badge>
          ) : (
            <Badge variant="secondary">미연동</Badge>
          )}
        </div>

        {justConnected && (
          <p className="text-sm text-emerald-500">유튜브 연동이 완료됐어요.</p>
        )}

        <Button asChild disabled={!API_BASE}>
          <a href={authHref}>{connected ? "유튜브 다시 연동" : "유튜브 연동"}</a>
        </Button>

        {!API_BASE && (
          <p className="text-xs text-muted-foreground">
            NEXT_PUBLIC_API_BASE_URL 이 설정되지 않아 연동 버튼을 사용할 수 없어요.
          </p>
        )}
      </div>
    </div>
  )
}
