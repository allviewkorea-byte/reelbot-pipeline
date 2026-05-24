"use client"

import { useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import {
  PlayCircle,
  Camera,
  Music2,
  Video,
  Plus,
  Users,
  DollarSign,
  Settings2,
  X,
} from "lucide-react"
import { useChannels } from "@/components/channels/ChannelProvider"
import {
  PLATFORM_LABELS,
  PLATFORM_BADGE,
  PLATFORM_ORDER,
  TRACK_LABELS,
  TRACK_BADGE,
  getDefaultRatio,
  type Channel,
  type Platform,
  type ContentType,
} from "@/lib/channels"

const PLATFORM_ICON: Record<Platform, React.ComponentType<{ className?: string; style?: React.CSSProperties }>> = {
  youtube: PlayCircle,
  instagram: Camera,
  tiktok: Music2,
  naverclip: Video,
}

function ChannelCard({ ch, onManage }: { ch: Channel; onManage: (id: string) => void }) {
  const Icon = PLATFORM_ICON[ch.platform]
  return (
    <div className="flex flex-col gap-4 rounded-xl border border-border bg-card p-5 transition-all hover:border-border/80">
      {/* Top: name + platform badge */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5 min-w-0">
          <div
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
            style={{ backgroundColor: `${ch.color}20`, border: `1px solid ${ch.color}40` }}
          >
            <Icon className="h-4 w-4" style={{ color: ch.color }} />
          </div>
          <p className="text-sm font-semibold text-foreground truncate">{ch.name}</p>
        </div>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${PLATFORM_BADGE[ch.platform]}`}>
          {PLATFORM_LABELS[ch.platform]}
        </span>
      </div>

      {/* Middle: main character avatar + track label */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div
            className="flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold text-white"
            style={{ backgroundColor: ch.color }}
          >
            {ch.character.slice(0, 1)}
          </div>
          <span className="text-xs text-muted-foreground">
            메인 캐릭터 <span className="font-medium text-foreground/80">{ch.character}</span>
          </span>
        </div>
        <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${TRACK_BADGE[ch.stack.track]}`}>
          {TRACK_LABELS[ch.stack.track]}
        </span>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-2 rounded-lg border border-border/60 bg-background/40 p-3 text-center">
        <div>
          <p className="text-xs text-muted-foreground">영상</p>
          <p className="mt-0.5 text-sm font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
            {ch.videos}개
          </p>
        </div>
        <div className="border-x border-border/60">
          <p className="text-xs text-muted-foreground">구독자</p>
          <p className="mt-0.5 text-sm font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
            {ch.subscribers}
          </p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">월 수익</p>
          <p className="mt-0.5 text-sm font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
            ${ch.revenue}
          </p>
        </div>
      </div>

      {/* Bottom: manage button */}
      <button
        onClick={() => onManage(ch.id)}
        className="flex items-center justify-center gap-1.5 rounded-lg border border-border py-2 text-sm font-medium text-foreground transition-all hover:border-primary/40 hover:bg-primary/5"
      >
        <Settings2 className="h-4 w-4" />
        관리
      </button>
    </div>
  )
}

function CreateChannelModal({ onClose }: { onClose: () => void }) {
  const { createChannel } = useChannels()
  const router = useRouter()
  const [name, setName] = useState("")
  const [platform, setPlatform] = useState<Platform>("youtube")
  const [contentType, setContentType] = useState<ContentType>("long")

  // 작업 2.5-5 · 플랫폼 + 콘텐츠 유형 → 비율 자동
  const ratio = getDefaultRatio(platform, contentType)
  const showContentType = platform === "youtube"
  const [creating, setCreating] = useState(false)

  async function submit() {
    const trimmed = name.trim()
    if (!trimmed || creating) return
    setCreating(true)
    try {
      const id = await createChannel({
        name: trimmed,
        platform,
        contentType: showContentType ? contentType : "short",
      })
      onClose()
      router.push(`/channels/${id}`)
    } catch {
      // createChannel 내부에서 토스트 표시 + 롤백 처리됨
      setCreating(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-foreground">새 채널 만들기</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground" aria-label="닫기">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex flex-col gap-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">채널 이름</label>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="예: 파리 브이로그"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary/50"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">플랫폼</label>
            <select
              value={platform}
              onChange={(e) => setPlatform(e.target.value as Platform)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary/50"
            >
              {PLATFORM_ORDER.map((p) => (
                <option key={p} value={p}>
                  {PLATFORM_LABELS[p]}
                </option>
              ))}
            </select>
          </div>

          {showContentType && (
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">콘텐츠 유형</label>
              <select
                value={contentType}
                onChange={(e) => setContentType(e.target.value as ContentType)}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary/50"
              >
                <option value="long">롱폼</option>
                <option value="short">숏폼</option>
              </select>
            </div>
          )}

          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">비율 (자동)</label>
            <input
              value={ratio}
              disabled
              readOnly
              className="w-full cursor-not-allowed rounded-lg border border-border bg-secondary/40 px-3 py-2 text-sm text-muted-foreground outline-none"
            />
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            취소
          </button>
          <button
            onClick={submit}
            disabled={!name.trim() || creating}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            {creating ? "만드는 중..." : "만들기"}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function ChannelsPage() {
  const { channels } = useChannels()
  const router = useRouter()
  const [filter, setFilter] = useState<Platform | "all">("all")
  const [showCreate, setShowCreate] = useState(false)

  const totals = useMemo(() => {
    const videos = channels.reduce((s, c) => s + c.videos, 0)
    const revenue = channels.reduce((s, c) => s + c.revenue, 0)
    return { count: channels.length, videos, revenue }
  }, [channels])

  const grouped = useMemo(() => {
    const visible = filter === "all" ? channels : channels.filter((c) => c.platform === filter)
    return PLATFORM_ORDER.map((p) => ({
      platform: p,
      items: visible.filter((c) => c.platform === p),
    })).filter((g) => g.items.length > 0)
  }, [channels, filter])

  const filters: Array<{ key: Platform | "all"; label: string }> = [
    { key: "all", label: "전체" },
    ...PLATFORM_ORDER.map((p) => ({ key: p, label: PLATFORM_LABELS[p] })),
  ]

  return (
    <div className="flex flex-1 flex-col gap-6 p-6 overflow-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">채널 관리</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            플랫폼별 채널을 컨테이너로 관리하고 스택을 설정합니다
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
        >
          <Plus className="h-4 w-4" />
          새 채널 만들기
        </button>
      </div>

      {/* Platform filter */}
      <div className="flex flex-wrap gap-2">
        {filters.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`rounded-full px-3.5 py-1.5 text-xs font-medium transition-colors ${
              filter === f.key
                ? "bg-primary/20 text-primary border border-primary/30"
                : "border border-border text-muted-foreground hover:text-foreground"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Grouped channel grid */}
      {grouped.length === 0 ? (
        <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-border py-16 text-sm text-muted-foreground">
          채널이 없습니다. 새 채널을 만들어 보세요.
        </div>
      ) : (
        grouped.map((group) => (
          <div key={group.platform} className="flex flex-col gap-3">
            <div className="flex items-center gap-2">
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${PLATFORM_BADGE[group.platform]}`}>
                {PLATFORM_LABELS[group.platform]}
              </span>
              <span className="text-xs text-muted-foreground">{group.items.length}개 채널</span>
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {group.items.map((ch) => (
                <ChannelCard key={ch.id} ch={ch} onManage={(id) => router.push(`/channels/${id}`)} />
              ))}
            </div>
          </div>
        ))
      )}

      {/* Summary Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Video className="h-4 w-4" />
            <span className="text-xs">운영 채널</span>
          </div>
          <p className="mt-2 text-2xl font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
            {totals.count}개
          </p>
        </div>
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Users className="h-4 w-4" />
            <span className="text-xs">총 영상</span>
          </div>
          <p className="mt-2 text-2xl font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
            {totals.videos}개
          </p>
        </div>
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center gap-2 text-muted-foreground">
            <DollarSign className="h-4 w-4" />
            <span className="text-xs">월 수익 합계</span>
          </div>
          <p className="mt-2 text-2xl font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
            ${totals.revenue}
          </p>
        </div>
      </div>

      {showCreate && <CreateChannelModal onClose={() => setShowCreate(false)} />}
    </div>
  )
}
