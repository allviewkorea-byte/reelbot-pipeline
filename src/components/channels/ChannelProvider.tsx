"use client"

import { createContext, useContext, useEffect, useRef, useState, useCallback } from "react"
import { toast } from "sonner"
import {
  DEFAULT_CHANNELS,
  getDefaultRatio,
  type Channel,
  type ContentType,
  type Platform,
  type StackConfig,
} from "@/lib/channels"

const NEW_CHANNEL_COLORS = ["#8b5cf6", "#06b6d4", "#f59e0b", "#ec4899", "#10b981"]

interface ChannelContextValue {
  channels: Channel[]
  hydrated: boolean
  getChannel: (id: string) => Channel | undefined
  createChannel: (input: {
    name: string
    platform: Platform
    contentType: ContentType
    character?: string
  }) => Promise<string>
  updateStack: (id: string, patch: Partial<StackConfig>) => Promise<void>
  updateChannel: (id: string, patch: Partial<Omit<Channel, "stack">>) => Promise<void>
  cloneChannel: (sourceId: string, newName: string) => Promise<string | null>
  deleteChannel: (id: string) => Promise<void>
}

const ChannelContext = createContext<ChannelContextValue | null>(null)

function genId(name: string): string {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9가-힣]+/g, "-")
    .replace(/^-+|-+$/g, "")
  return `${slug || "channel"}-${Date.now().toString(36)}`
}

export function ChannelProvider({ children }: { children: React.ReactNode }) {
  // 서버(Supabase)가 단일 진실 원천. 로드 전 첫 페인트는 기본 채널을 보여주고,
  // 로드 완료 시 서버 데이터로 교체한다. 읽기(channels/getChannel)는 동기 유지.
  const [channels, setChannels] = useState<Channel[]>(DEFAULT_CHANNELS)
  const [hydrated, setHydrated] = useState(false)

  // 안정적인 콜백 안에서 항상 최신 channels 를 읽기 위한 ref 미러.
  const channelsRef = useRef(channels)
  useEffect(() => {
    channelsRef.current = channels
  }, [channels])

  // 서버에서 채널 목록을 다시 불러와 로컬 상태와 정합화 (낙관적 변경 실패 시 복구용).
  const reload = useCallback(async () => {
    try {
      const res = await fetch("/api/channels", { cache: "no-store" })
      const data = await res.json()
      if (data?.success && Array.isArray(data.channels)) {
        setChannels(data.channels)
      }
    } catch {
      /* 네트워크 실패는 무시 (기존 로컬 상태 유지) */
    }
  }, [])

  // 최초 1회 서버 로드. setState 는 fetch 콜백(비동기) 안에서만 호출한다.
  useEffect(() => {
    let cancelled = false
    fetch("/api/channels", { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => {
        if (cancelled) return
        if (d?.success && Array.isArray(d.channels) && d.channels.length > 0) {
          setChannels(d.channels)
        }
      })
      .catch(() => {
        /* 로드 실패 시 기본 채널 유지 */
      })
      .finally(() => {
        if (!cancelled) setHydrated(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const getChannel = useCallback(
    (id: string) => channels.find((c) => c.id === id),
    [channels]
  )

  const createChannel = useCallback<ChannelContextValue["createChannel"]>(
    async ({ name, platform, contentType, character }) => {
      const channel: Channel = {
        id: genId(name),
        name,
        platform,
        character: character || "지수",
        subscribers: "0",
        videos: 0,
        revenue: 0,
        avgViews: "0",
        status: "준비 중",
        statusVariant: "pending",
        color: NEW_CHANNEL_COLORS[Math.floor(Math.random() * NEW_CHANNEL_COLORS.length)],
        stack: {
          track: "auto",
          characters: character ? [character] : ["지수"],
          scenarioTone: "여행",
          storyboardModel: "gpt-image-1",
          videoModel: "kling-v1",
          subtitleStyle: "basic",
          publishTargets: [platform],
          schedule: "매일 09시",
          contentType,
          ratio: getDefaultRatio(platform, contentType),
          ratioOverride: false,
          fullAuto: false,
        },
      }
      // 낙관적 추가 → 이동 시 즉시 조회 가능.
      setChannels((prev) => [...prev, channel])
      try {
        const res = await fetch("/api/channels", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(channel),
        })
        const data = await res.json()
        if (!res.ok || !data.success) throw new Error(data.error || "채널 저장 실패")
      } catch (err) {
        setChannels((prev) => prev.filter((c) => c.id !== channel.id)) // 롤백
        toast.error(err instanceof Error ? err.message : "채널 저장에 실패했습니다")
        throw err
      }
      return channel.id
    },
    []
  )

  // 변경분을 서버에 반영(PATCH). 실패 시 서버 상태로 정합화하고 알림.
  const persistPatch = useCallback(
    async (channel: Channel) => {
      try {
        const res = await fetch(`/api/channels/${encodeURIComponent(channel.id)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(channel),
        })
        const data = await res.json()
        if (!res.ok || !data.success) throw new Error(data.error || "채널 저장 실패")
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "채널 저장에 실패했습니다")
        await reload()
      }
    },
    [reload]
  )

  const updateStack = useCallback<ChannelContextValue["updateStack"]>(
    async (id, patch) => {
      const current = channelsRef.current.find((c) => c.id === id)
      if (!current) return
      const updated: Channel = { ...current, stack: { ...current.stack, ...patch } }
      setChannels((prev) => prev.map((c) => (c.id === id ? updated : c)))
      await persistPatch(updated)
    },
    [persistPatch]
  )

  const updateChannel = useCallback<ChannelContextValue["updateChannel"]>(
    async (id, patch) => {
      const current = channelsRef.current.find((c) => c.id === id)
      if (!current) return
      const updated: Channel = { ...current, ...patch }
      setChannels((prev) => prev.map((c) => (c.id === id ? updated : c)))
      await persistPatch(updated)
    },
    [persistPatch]
  )

  const cloneChannel = useCallback<ChannelContextValue["cloneChannel"]>(
    async (sourceId, newName) => {
      const source = channelsRef.current.find((c) => c.id === sourceId)
      if (!source) return null
      const clone: Channel = {
        ...source,
        id: genId(newName),
        name: newName,
        // 통계는 0으로 초기화
        subscribers: "0",
        videos: 0,
        revenue: 0,
        avgViews: "0",
        status: "준비 중",
        statusVariant: "pending",
        // 스택 설정은 모두 복사 (깊은 복사)
        stack: {
          ...source.stack,
          characters: [...source.stack.characters],
          publishTargets: [...source.stack.publishTargets],
        },
      }
      setChannels((prev) => [...prev, clone])
      try {
        const res = await fetch("/api/channels", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(clone),
        })
        const data = await res.json()
        if (!res.ok || !data.success) throw new Error(data.error || "채널 저장 실패")
      } catch (err) {
        setChannels((prev) => prev.filter((c) => c.id !== clone.id)) // 롤백
        toast.error(err instanceof Error ? err.message : "채널 복제에 실패했습니다")
        return null
      }
      return clone.id
    },
    []
  )

  const deleteChannel = useCallback<ChannelContextValue["deleteChannel"]>(async (id) => {
    const snapshot = channelsRef.current
    setChannels((prev) => prev.filter((c) => c.id !== id)) // 낙관적 삭제
    try {
      const res = await fetch(`/api/channels/${encodeURIComponent(id)}`, { method: "DELETE" })
      const data = await res.json()
      if (!res.ok || !data.success) throw new Error(data.error || "채널 삭제 실패")
    } catch (err) {
      setChannels(snapshot) // 롤백
      toast.error(err instanceof Error ? err.message : "채널 삭제에 실패했습니다")
    }
  }, [])

  return (
    <ChannelContext.Provider
      value={{
        channels,
        hydrated,
        getChannel,
        createChannel,
        updateStack,
        updateChannel,
        cloneChannel,
        deleteChannel,
      }}
    >
      {children}
    </ChannelContext.Provider>
  )
}

export function useChannels(): ChannelContextValue {
  const ctx = useContext(ChannelContext)
  if (!ctx) {
    throw new Error("useChannels must be used within ChannelProvider")
  }
  return ctx
}

export { getDefaultRatio }
