"use client"

import { useEffect, useMemo, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import Link from "next/link"
import { toast } from "sonner"
import {
  ArrowLeft,
  Trash2,
  Copy,
  X,
  Users,
  Video,
  DollarSign,
  Eye,
  Film,
  Bot,
  Camera,
  Scissors,
  Clapperboard,
} from "lucide-react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useChannels } from "@/components/channels/ChannelProvider"
import {
  PLATFORM_LABELS,
  PLATFORM_BADGE,
  PLATFORM_ORDER,
  TRACK_LABELS,
  TRACK_BADGE,
  SCENARIO_TONES,
  STORYBOARD_MODELS,
  VIDEO_MODELS,
  SUBTITLE_STYLES,
  CHARACTER_OPTIONS,
  getDefaultRatio,
  type Track,
  type Platform,
  type ContentType,
  type StackConfig,
} from "@/lib/channels"

const TRACKS: Array<{ id: Track; label: string; desc: string; icon: React.ComponentType<{ className?: string }> }> = [
  { id: "auto", label: TRACK_LABELS.auto, desc: "AI가 대본·콘티·영상·업로드까지 24/7 처리", icon: Bot },
  { id: "semi", label: TRACK_LABELS.semi, desc: "직접 촬영한 실제 공간 영상에 자동 편집 결합", icon: Camera },
  { id: "adobe", label: TRACK_LABELS.adobe, desc: "어도비 편집 워크플로로 정교하게 다듬기", icon: Scissors },
]

function recentVideos(name: string, count: number) {
  const titles = ["오프닝 인트로", "메인 스팟 소개", "현지 음식 체험", "야경 브이로그", "마무리 아웃트로"]
  const n = Math.min(count, 5)
  return Array.from({ length: n }, (_, i) => ({
    id: `${name}-${i}`,
    title: titles[i % titles.length],
    views: `${(Math.max(count - i, 1) * 37) % 900 + 80}회`,
  }))
}

export default function ChannelDetailPage() {
  const params = useParams<{ id: string }>()
  const id = params.id
  const router = useRouter()
  const { getChannel, updateStack, deleteChannel, cloneChannel, hydrated } = useChannels()
  const channel = getChannel(id)

  const [draft, setDraft] = useState<StackConfig | null>(channel ? channel.stack : null)
  const [showClone, setShowClone] = useState(false)

  useEffect(() => {
    if (channel) setDraft(channel.stack)
    // 채널 변경 시 드래프트 동기화
  }, [channel?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const recents = useMemo(() => (channel ? recentVideos(channel.id, channel.videos) : []), [channel])

  if (!channel || !draft) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6">
        <p className="text-sm text-muted-foreground">
          {hydrated ? "채널을 찾을 수 없습니다." : "불러오는 중…"}
        </p>
        <Link href="/channels" className="text-sm text-primary hover:underline">
          채널 목록으로 돌아가기
        </Link>
      </div>
    )
  }

  function patch(p: Partial<StackConfig>) {
    setDraft((d) => (d ? { ...d, ...p } : d))
  }

  function toggleCharacter(name: string) {
    setDraft((d) => {
      if (!d) return d
      const has = d.characters.includes(name)
      const next = has ? d.characters.filter((c) => c !== name) : [...d.characters, name]
      return { ...d, characters: next.length ? next : d.characters }
    })
  }

  function setContentType(ct: ContentType) {
    setDraft((d) => {
      if (!d) return d
      const ratio = d.ratioOverride ? d.ratio : getDefaultRatio(channel!.platform, ct)
      return { ...d, contentType: ct, ratio }
    })
  }

  function setOverride(on: boolean) {
    setDraft((d) => {
      if (!d) return d
      const ratio = on ? d.ratio : getDefaultRatio(channel!.platform, d.contentType)
      return { ...d, ratioOverride: on, ratio }
    })
  }

  function togglePublish(p: Platform) {
    setDraft((d) => {
      if (!d) return d
      const has = d.publishTargets.includes(p)
      return { ...d, publishTargets: has ? d.publishTargets.filter((x) => x !== p) : [...d.publishTargets, p] }
    })
  }

  function save() {
    updateStack(channel!.id, draft!)
    toast.success("스택 설정을 저장했습니다")
  }

  function handleDelete() {
    if (confirm(`'${channel!.name}' 채널을 삭제할까요? 되돌릴 수 없습니다.`)) {
      deleteChannel(channel!.id)
      toast.success("채널을 삭제했습니다")
      router.push("/channels")
    }
  }

  function startWorkflow() {
    const cid = channel!.id
    const map: Record<Track, string> = {
      auto: `/video?channel=${cid}&mode=auto`,
      semi: `/space?channel=${cid}`,
      adobe: `/adobe?channel=${cid}`,
    }
    router.push(map[draft!.track])
  }

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-auto p-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <Link
            href="/channels"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border text-muted-foreground transition-colors hover:text-foreground"
            aria-label="채널 목록으로"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-semibold text-foreground truncate">{channel.name}</h1>
              <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${PLATFORM_BADGE[channel.platform]}`}>
                {PLATFORM_LABELS[channel.platform]}
              </span>
              <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${TRACK_BADGE[channel.stack.track]}`}>
                {TRACK_LABELS[channel.stack.track]}
              </span>
            </div>
            <p className="mt-0.5 text-sm text-muted-foreground">메인 캐릭터 {channel.character}</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            onClick={() => setShowClone(true)}
            className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-primary/5"
          >
            <Copy className="h-4 w-4" />
            이 채널 복제
          </button>
          <button
            onClick={handleDelete}
            className="flex items-center gap-1.5 rounded-lg border border-red-500/30 px-3 py-2 text-sm font-medium text-red-400 transition-colors hover:bg-red-500/10"
          >
            <Trash2 className="h-4 w-4" />
            채널 삭제
          </button>
        </div>
      </div>

      {showClone && (
        <CloneModal
          defaultName={`${channel.name} 복사본`}
          onClose={() => setShowClone(false)}
          onConfirm={(newName) => {
            const newId = cloneChannel(channel.id, newName)
            setShowClone(false)
            if (newId) {
              toast.success("채널을 복제했습니다")
              router.push(`/channels/${newId}`)
            }
          }}
        />
      )}

      <Tabs defaultValue="overview" className="w-full">
        <TabsList>
          <TabsTrigger value="overview">개요</TabsTrigger>
          <TabsTrigger value="stack">스택 설정</TabsTrigger>
          <TabsTrigger value="workflow">워크플로</TabsTrigger>
          <TabsTrigger value="history">히스토리</TabsTrigger>
        </TabsList>

        {/* 탭 1: 개요 */}
        <TabsContent value="overview" className="mt-4 flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            {[
              { label: "영상 수", value: `${channel.videos}개`, icon: Video },
              { label: "구독자", value: channel.subscribers, icon: Users },
              { label: "월 수익", value: `$${channel.revenue}`, icon: DollarSign },
              { label: "평균 조회수", value: channel.avgViews, icon: Eye },
            ].map((s) => (
              <div key={s.label} className="rounded-xl border border-border bg-card p-4">
                <div className="flex items-center gap-2 text-muted-foreground">
                  <s.icon className="h-4 w-4" />
                  <span className="text-xs">{s.label}</span>
                </div>
                <p className="mt-2 text-xl font-bold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
                  {s.value}
                </p>
              </div>
            ))}
          </div>

          <div className="rounded-xl border border-border bg-card p-5">
            <h2 className="mb-3 text-sm font-semibold text-foreground">최근 영상</h2>
            <div className="flex flex-col gap-2">
              {recents.length === 0 ? (
                <p className="text-sm text-muted-foreground">아직 영상이 없습니다.</p>
              ) : (
                recents.map((v) => (
                  <div key={v.id} className="flex items-center gap-3 rounded-lg border border-border/60 p-2.5">
                    <div className="flex h-10 w-16 shrink-0 items-center justify-center rounded-md bg-secondary/50">
                      <Film className="h-4 w-4 text-muted-foreground" />
                    </div>
                    <span className="flex-1 text-sm text-foreground">{v.title}</span>
                    <span className="text-xs text-muted-foreground">{v.views}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </TabsContent>

        {/* 탭 2: 스택 설정 */}
        <TabsContent value="stack" className="mt-4 flex flex-col gap-4">
          {/* 트랙 선택 */}
          <div className="rounded-xl border border-border bg-card p-5">
            <h2 className="mb-3 text-sm font-semibold text-foreground">트랙</h2>
            <div className="flex flex-col gap-2">
              {TRACKS.map((t) => {
                const active = draft.track === t.id
                return (
                  <button
                    key={t.id}
                    onClick={() => patch({ track: t.id })}
                    className={`flex items-center gap-3 rounded-lg border p-3.5 text-left transition-all ${
                      active ? "border-primary/40 bg-primary/5" : "border-border hover:bg-secondary/30"
                    }`}
                  >
                    <div className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 ${active ? "border-primary" : "border-muted-foreground/40"}`}>
                      {active && <div className="h-2 w-2 rounded-full bg-primary" />}
                    </div>
                    <div className="flex-1">
                      <p className={`text-sm font-semibold ${active ? "text-foreground" : "text-muted-foreground"}`}>{t.label}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">{t.desc}</p>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>

          {/* 캐릭터 묶음 */}
          <div className="rounded-xl border border-border bg-card p-5">
            <h2 className="mb-3 text-sm font-semibold text-foreground">캐릭터 묶음</h2>
            <div className="flex flex-wrap gap-2">
              {CHARACTER_OPTIONS.map((name) => {
                const on = draft.characters.includes(name)
                return (
                  <button
                    key={name}
                    onClick={() => toggleCharacter(name)}
                    className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                      on ? "bg-primary/20 text-primary border border-primary/30" : "border border-border text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {name}
                  </button>
                )
              })}
            </div>
          </div>

          {/* 드롭다운 설정들 */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Field label="시나리오 톤">
              <Select value={draft.scenarioTone} onChange={(v) => patch({ scenarioTone: v })}>
                {SCENARIO_TONES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </Select>
            </Field>

            <Field label="콘티 모델">
              <Select value={draft.storyboardModel} onChange={(v) => patch({ storyboardModel: v })}>
                {STORYBOARD_MODELS.map((m) => (
                  <option key={m.value} value={m.value} disabled={m.disabled}>{m.label}</option>
                ))}
              </Select>
            </Field>

            <Field label="영상 모델">
              <Select value={draft.videoModel} onChange={(v) => patch({ videoModel: v })}>
                {VIDEO_MODELS.map((m) => (
                  <option key={m.value} value={m.value} disabled={m.disabled}>{m.label}</option>
                ))}
              </Select>
            </Field>

            <Field label="자막 스타일">
              <Select value={draft.subtitleStyle} onChange={(v) => patch({ subtitleStyle: v })}>
                {SUBTITLE_STYLES.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </Select>
            </Field>

            <Field label="업로드 스케줄">
              <input
                value={draft.schedule}
                onChange={(e) => patch({ schedule: e.target.value })}
                placeholder="예: 매일 09시"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary/50"
              />
            </Field>
          </div>

          {/* 비율 자동 매핑 (작업 2.5-5) */}
          <div className="rounded-xl border border-border bg-card p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-foreground">화면 비율</h2>
              <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={draft.ratioOverride}
                  onChange={(e) => setOverride(e.target.checked)}
                  className="h-4 w-4 accent-[var(--primary)]"
                />
                수동 override
              </label>
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {channel.platform === "youtube" && (
                <div>
                  <label className="mb-1.5 block text-xs font-medium text-muted-foreground">콘텐츠 유형</label>
                  <Select value={draft.contentType} onChange={(v) => setContentType(v as ContentType)}>
                    <option value="long">롱폼</option>
                    <option value="short">숏폼</option>
                  </Select>
                </div>
              )}
              <div>
                <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                  비율{draft.ratioOverride ? "" : " (자동)"}
                </label>
                <input
                  value={draft.ratio}
                  readOnly={!draft.ratioOverride}
                  disabled={!draft.ratioOverride}
                  onChange={(e) => patch({ ratio: e.target.value })}
                  className={`w-full rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-primary/50 ${
                    draft.ratioOverride
                      ? "bg-background text-foreground"
                      : "cursor-not-allowed bg-secondary/40 text-muted-foreground"
                  }`}
                />
              </div>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {PLATFORM_LABELS[channel.platform]} 기본 비율: {getDefaultRatio(channel.platform, draft.contentType)}
            </p>
          </div>

          {/* 완전 자동 모드 */}
          <div className="rounded-xl border border-border bg-card p-5">
            <h2 className="mb-3 text-sm font-semibold text-foreground">자동화 수준</h2>
            <label className="flex cursor-pointer items-start gap-2.5 text-sm text-foreground">
              <input
                type="checkbox"
                checked={draft.fullAuto ?? false}
                onChange={(e) => patch({ fullAuto: e.target.checked })}
                className="mt-0.5 h-4 w-4 accent-[var(--primary)]"
              />
              <span>
                완전 자동 모드 (콘티 검토 없이 영상 자동 진행)
                <span className="mt-1 block text-xs text-muted-foreground">
                  체크 해제 시(기본값) 콘티 생성 후 검토·확인을 거쳐 사용자가 영상 생성을 시작합니다.
                  체크 시 콘티 완료 즉시 영상(비용 높음)이 자동으로 시작됩니다.
                </span>
              </span>
            </label>
          </div>

          {/* 발행 채널 매핑 */}
          <div className="rounded-xl border border-border bg-card p-5">
            <h2 className="mb-3 text-sm font-semibold text-foreground">발행 채널 매핑</h2>
            <div className="flex flex-wrap gap-3">
              {PLATFORM_ORDER.map((p) => {
                const on = draft.publishTargets.includes(p)
                return (
                  <label key={p} className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
                    <input
                      type="checkbox"
                      checked={on}
                      onChange={() => togglePublish(p)}
                      className="h-4 w-4 accent-[var(--primary)]"
                    />
                    {PLATFORM_LABELS[p]}
                  </label>
                )
              })}
            </div>
          </div>

          <div className="flex justify-end">
            <button
              onClick={save}
              className="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
            >
              스택 설정 저장
            </button>
          </div>
        </TabsContent>

        {/* 탭 3: 워크플로 */}
        <TabsContent value="workflow" className="mt-4 flex flex-col gap-4">
          <button
            onClick={startWorkflow}
            className="flex items-center justify-center gap-2 rounded-xl bg-primary px-6 py-5 text-base font-semibold text-primary-foreground transition-opacity hover:opacity-90"
          >
            <Clapperboard className="h-5 w-5" />
            영상 만들기 ({TRACK_LABELS[draft.track]})
          </button>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {TRACKS.map((t) => {
              const active = draft.track === t.id
              return (
                <div
                  key={t.id}
                  className={`rounded-xl border bg-card p-4 ${active ? "border-primary/40" : "border-border"}`}
                >
                  <div className="flex items-center gap-2">
                    <t.icon className="h-4 w-4 text-primary" />
                    <span className="text-sm font-semibold text-foreground">{t.label}</span>
                    {active && (
                      <span className="ml-auto rounded-full bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary">
                        현재 트랙
                      </span>
                    )}
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">{t.desc}</p>
                </div>
              )
            })}
          </div>
        </TabsContent>

        {/* 탭 4: 히스토리 */}
        <TabsContent value="history" className="mt-4">
          <div className="rounded-xl border border-border bg-card p-5">
            <h2 className="mb-3 text-sm font-semibold text-foreground">{channel.name} 영상 ({channel.videos}개)</h2>
            <div className="flex flex-col gap-2">
              {recents.length === 0 ? (
                <p className="text-sm text-muted-foreground">아직 생성된 영상이 없습니다.</p>
              ) : (
                recents.map((v) => (
                  <div key={v.id} className="flex items-center gap-3 rounded-lg border border-border/60 p-2.5">
                    <div className="flex h-10 w-16 shrink-0 items-center justify-center rounded-md bg-secondary/50">
                      <Film className="h-4 w-4 text-muted-foreground" />
                    </div>
                    <span className="flex-1 text-sm text-foreground">{v.title}</span>
                    <span className="text-xs text-muted-foreground">{v.views}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}

function CloneModal({
  defaultName,
  onClose,
  onConfirm,
}: {
  defaultName: string
  onClose: () => void
  onConfirm: (name: string) => void
}) {
  const [name, setName] = useState(defaultName)
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-foreground">채널 복제</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground" aria-label="닫기">
            <X className="h-4 w-4" />
          </button>
        </div>
        <p className="mb-3 text-xs text-muted-foreground">
          스택 설정(트랙·캐릭터·모델·자막·발행·스케줄)은 그대로 복사되고, 통계는 0으로 초기화됩니다.
        </p>
        <label className="mb-1.5 block text-xs font-medium text-muted-foreground">새 채널 이름</label>
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary/50"
        />
        <div className="mt-6 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            취소
          </button>
          <button
            onClick={() => onConfirm(name.trim() || defaultName)}
            disabled={!name.trim()}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            복제하기
          </button>
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <label className="mb-1.5 block text-xs font-medium text-muted-foreground">{label}</label>
      {children}
    </div>
  )
}

function Select({
  value,
  onChange,
  children,
}: {
  value: string
  onChange: (v: string) => void
  children: React.ReactNode
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-primary/50"
    >
      {children}
    </select>
  )
}
