"use client"

import { createContext, useContext, useEffect, useState, useCallback } from "react"
import {
  DEFAULT_CHANNELS,
  getDefaultRatio,
  type Channel,
  type ContentType,
  type Platform,
  type StackConfig,
} from "@/lib/channels"

const NEW_CHANNEL_COLORS = ["#8b5cf6", "#06b6d4", "#f59e0b", "#ec4899", "#10b981"]

const STORAGE_KEY = "reelbot.channels.v1"

interface ChannelContextValue {
  channels: Channel[]
  hydrated: boolean
  getChannel: (id: string) => Channel | undefined
  createChannel: (input: {
    name: string
    platform: Platform
    contentType: ContentType
    character?: string
  }) => string
  updateStack: (id: string, patch: Partial<StackConfig>) => void
  updateChannel: (id: string, patch: Partial<Omit<Channel, "stack">>) => void
  cloneChannel: (sourceId: string, newName: string) => string | null
  deleteChannel: (id: string) => void
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
  const [channels, setChannels] = useState<Channel[]>(DEFAULT_CHANNELS)
  const [hydrated, setHydrated] = useState(false)

  // 마이그레이션: 기존 데이터(채널 3개)를 새 스키마로 보존, 손실 없음
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) {
        const parsed = JSON.parse(raw) as Channel[]
        if (Array.isArray(parsed) && parsed.length > 0) {
          setChannels(parsed)
        }
      }
    } catch {
      // 손상된 저장값은 무시하고 기본 데이터 유지
    }
    setHydrated(true)
  }, [])

  useEffect(() => {
    if (!hydrated) return
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(channels))
    } catch {
      // 저장 실패는 무시 (메모리 상태는 유지)
    }
  }, [channels, hydrated])

  const getChannel = useCallback(
    (id: string) => channels.find((c) => c.id === id),
    [channels]
  )

  const createChannel = useCallback<ChannelContextValue["createChannel"]>(
    ({ name, platform, contentType, character }) => {
      const newId = genId(name)
      const channel: Channel = {
        id: newId,
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
        },
      }
      setChannels((prev) => [...prev, channel])
      return newId
    },
    []
  )

  const updateStack = useCallback((id: string, patch: Partial<StackConfig>) => {
    setChannels((prev) =>
      prev.map((c) => (c.id === id ? { ...c, stack: { ...c.stack, ...patch } } : c))
    )
  }, [])

  const updateChannel = useCallback(
    (id: string, patch: Partial<Omit<Channel, "stack">>) => {
      setChannels((prev) => prev.map((c) => (c.id === id ? { ...c, ...patch } : c)))
    },
    []
  )

  const cloneChannel = useCallback(
    (sourceId: string, newName: string): string | null => {
      const source = channels.find((c) => c.id === sourceId)
      if (!source) return null
      const newId = genId(newName)
      const clone: Channel = {
        ...source,
        id: newId,
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
      return newId
    },
    [channels]
  )

  const deleteChannel = useCallback((id: string) => {
    setChannels((prev) => prev.filter((c) => c.id !== id))
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
