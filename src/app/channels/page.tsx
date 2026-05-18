"use client"

import { PlayCircle, MoreHorizontal, Plus, Users, Video, DollarSign } from "lucide-react"

const CHANNELS = [
  {
    id: "bangkok",
    name: "방콕 여행 채널",
    character: "지수",
    subscribers: "2.1K",
    videos: 54,
    status: "활성",
    statusVariant: "active" as const,
    color: "#8b5cf6",
  },
  {
    id: "tokyo",
    name: "도쿄 일상 브이로그",
    character: "하은",
    subscribers: "1.8K",
    videos: 48,
    status: "활성",
    statusVariant: "active" as const,
    color: "#06b6d4",
  },
  {
    id: "europe",
    name: "유럽 감성 여행",
    character: "지수",
    subscribers: "890",
    videos: 25,
    status: "준비 중",
    statusVariant: "pending" as const,
    color: "#f59e0b",
  },
]

const SUMMARY_STATS = [
  { label: "총 구독자", value: "4.8K", icon: Users },
  { label: "총 영상", value: "127개", icon: Video },
  { label: "이번 달 수익", value: "$127", icon: DollarSign },
]

export default function ChannelsPage() {
  return (
    <div className="flex flex-1 flex-col gap-6 p-6 overflow-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">채널 관리</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            YouTube 채널 연결 및 업로드 설정
          </p>
        </div>
        <button className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90">
          <Plus className="h-4 w-4" />
          채널 추가
        </button>
      </div>

      {/* Channel List */}
      <div className="flex flex-col gap-3">
        {CHANNELS.map((ch) => (
          <div
            key={ch.id}
            className="flex items-center gap-4 rounded-xl border border-border bg-card px-5 py-4 transition-all hover:border-border/80"
          >
            {/* YouTube icon with channel color */}
            <div
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
              style={{ backgroundColor: `${ch.color}20`, border: `1px solid ${ch.color}40` }}
            >
              <PlayCircle className="h-5 w-5" style={{ color: ch.color }} />
            </div>

            {/* Channel info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold text-foreground truncate">{ch.name}</p>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
                    ch.statusVariant === "active"
                      ? "bg-emerald-500/15 text-emerald-400"
                      : "bg-amber-500/15 text-amber-400"
                  }`}
                >
                  {ch.status}
                </span>
              </div>
              <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <span className="text-muted-foreground/60">캐릭터</span>
                  <span className="font-medium text-foreground/80">{ch.character}</span>
                </span>
                <span className="text-border">·</span>
                <span className="flex items-center gap-1">
                  <Users className="h-3 w-3" />
                  {ch.subscribers}
                </span>
                <span className="text-border">·</span>
                <span className="flex items-center gap-1">
                  <Video className="h-3 w-3" />
                  {ch.videos}개
                </span>
              </div>
            </div>

            {/* Settings button */}
            <button className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-muted-foreground transition-all hover:border-border/80 hover:text-foreground">
              <MoreHorizontal className="h-4 w-4" />
            </button>
          </div>
        ))}

        {/* Add channel placeholder */}
        <button className="flex items-center justify-center gap-2 rounded-xl border border-dashed border-border py-4 text-sm text-muted-foreground transition-all hover:border-primary/40 hover:text-foreground">
          <Plus className="h-4 w-4" />
          새 채널 연결
        </button>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-3 gap-4">
        {SUMMARY_STATS.map((stat) => (
          <div
            key={stat.label}
            className="rounded-xl border border-border bg-card p-4"
          >
            <div className="flex items-center gap-2 text-muted-foreground">
              <stat.icon className="h-4 w-4" />
              <span className="text-xs">{stat.label}</span>
            </div>
            <p
              className="mt-2 text-2xl font-bold text-foreground"
              style={{ fontFamily: "var(--font-geist-mono)" }}
            >
              {stat.value}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
