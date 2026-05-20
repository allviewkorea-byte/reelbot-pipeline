"use client"

import { useEffect, useRef, useState } from "react"
import { healthCheck } from "@/lib/api"

export type HealthState = "checking" | "online" | "offline"

// 백엔드 /health 를 주기적으로 폴링한다.
export function useHealthCheck(intervalMs = 5000) {
  const [state, setState] = useState<HealthState>("checking")
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let cancelled = false

    const check = async () => {
      try {
        const res = await healthCheck()
        if (!cancelled) setState(res.status === "ok" ? "online" : "offline")
      } catch {
        if (!cancelled) setState("offline")
      }
      if (!cancelled) timer.current = setTimeout(check, intervalMs)
    }

    check()

    return () => {
      cancelled = true
      if (timer.current) clearTimeout(timer.current)
    }
  }, [intervalMs])

  return state
}
