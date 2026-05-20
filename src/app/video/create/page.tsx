"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Wand2, AlertTriangle, ArrowLeft, DollarSign } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { useStoryboard } from "@/hooks/useStoryboard"
import { useVideoGeneration } from "@/hooks/useVideoGeneration"
import { generateScenario, type Scene } from "@/lib/api"
import { StoryboardReview } from "@/components/video/StoryboardReview"
import { ProgressTracker } from "@/components/video/ProgressTracker"
import { ResultViewer } from "@/components/video/ResultViewer"
import type { SceneStatus } from "@/components/video/SceneCard"
import { useChannels } from "@/components/channels/ChannelProvider"
import {
  STORYBOARD_MODELS,
  VIDEO_MODELS,
  TRACK_LABELS,
  storyboardCost,
  videoCost,
  type Track,
} from "@/lib/channels"

type Phase = "input" | "storyboard" | "generating" | "done"

const DURATION_OPTIONS = [
  { label: "1분 (6씬)", min: 1, scenes: 6 },
  { label: "2분 (12씬)", min: 2, scenes: 12 },
  { label: "4분 (24씬)", min: 4, scenes: 24 },
]

const DEFAULT_STORYBOARD_MODEL = "gpt-image-1"
const DEFAULT_VIDEO_MODEL = "kling-v1"
const ASSUMED_SEC_PER_SCENE = 5

function modelLabel(list: ReadonlyArray<{ value: string; label: string }>, value: string): string {
  return list.find((m) => m.value === value)?.label ?? value
}

export default function VideoCreatePage() {
  const [phase, setPhase] = useState<Phase>("input")
  const [country, setCountry] = useState("")
  const [durationMin, setDurationMin] = useState(2)
  const [preparingScenario, setPreparingScenario] = useState(false)

  const [scenes, setScenes] = useState<Scene[]>([])
  const [statuses, setStatuses] = useState<Record<string, SceneStatus>>({})

  // ?channel= 로 진입하면 해당 채널 스택(모델/트랙)을 적용한다. (클라이언트에서만 읽음)
  const { getChannel } = useChannels()
  const [channelId, setChannelId] = useState<string | null>(null)
  useEffect(() => {
    const cid = new URLSearchParams(window.location.search).get("channel")
    setChannelId(cid)
  }, [])
  const channel = channelId ? getChannel(channelId) : undefined

  const storyboardModel = channel?.stack.storyboardModel ?? DEFAULT_STORYBOARD_MODEL
  const videoModel = channel?.stack.videoModel ?? DEFAULT_VIDEO_MODEL
  // 트랙이 'auto'(자동화)면 콘티 완료 후 영상 단계로 자동 진행. 채널 없이 단독 진입 시 수동.
  const track: Track | null = channel?.stack.track ?? null
  const isAutoTrack = track === "auto"

  const storyboard = useStoryboard()
  const video = useVideoGeneration()

  // 비용 추정: 콘티 단계 전엔 길이 옵션의 씬 수로, 이후엔 실제 씬으로 계산.
  const expectedScenes =
    DURATION_OPTIONS.find((o) => o.min === durationMin)?.scenes ?? 12
  const sceneCount = scenes.length || expectedScenes
  const totalSeconds = scenes.length
    ? scenes.reduce((sum, s) => sum + (s.duration_sec ?? ASSUMED_SEC_PER_SCENE), 0)
    : sceneCount * ASSUMED_SEC_PER_SCENE
  const contiCost = storyboardCost(storyboardModel, sceneCount)
  const videoEst = videoCost(videoModel, totalSeconds)

  // ── 콘티 생성: 시나리오 → 씬 리스트 → 콘티 이미지 ──
  const handleStartStoryboard = useCallback(async () => {
    if (!country.trim()) {
      toast.error("여행지(국가/도시)를 입력해주세요.")
      return
    }
    setPreparingScenario(true)
    try {
      const res = await generateScenario({ country: country.trim(), duration_min: durationMin })
      const sc = res.scenes ?? []
      if (sc.length === 0) {
        toast.error("시나리오 씬을 받지 못했습니다. 백엔드 응답을 확인해주세요.")
        return
      }
      setScenes(sc)
      setStatuses(
        Object.fromEntries(sc.map((s) => [String(s.scene_id), "pending" as SceneStatus])),
      )
      setPhase("storyboard")
      await storyboard.generate({
        scenario: res.scenario ?? "",
        scenes: sc,
        storyboard_model: storyboardModel,
      })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "콘티 생성에 실패했습니다.")
    } finally {
      setPreparingScenario(false)
    }
  }, [country, durationMin, storyboard, storyboardModel])

  const handleApprove = useCallback((sceneId: string) => {
    setStatuses((prev) => ({
      ...prev,
      [sceneId]: prev[sceneId] === "approved" ? "pending" : "approved",
    }))
  }, [])

  const handleRegenerate = useCallback(
    async (sceneId: string, extra?: string) => {
      const scene = scenes.find((s) => String(s.scene_id) === sceneId)
      if (!scene) return
      setStatuses((prev) => ({ ...prev, [sceneId]: "regenerating" }))
      const numericId = scene.scene_id
      await storyboard.regenerate(numericId, scene as unknown as Record<string, unknown>, {
        storyboardJobId: storyboard.job?.job_id,
        extraInstructions: extra ?? null,
        storyboardModel,
      })
      setStatuses((prev) => ({ ...prev, [sceneId]: "pending" }))
      toast.success(`${sceneId} 재생성 완료`)
    },
    [scenes, storyboard, storyboardModel],
  )

  const autoStartedRef = useRef(false)
  const handleStartVideo = useCallback(async () => {
    setPhase("generating")
    await video.start({
      job_id: storyboard.job?.job_id ?? "",
      scenes: scenes as unknown as Record<string, unknown>[],
      approved_storyboards: storyboard.storyboards,
      scenario_mode: "B",
      seedance_mode: "kie",
      video_model: videoModel,
    })
  }, [scenes, storyboard, video, videoModel])

  // 자동화 트랙: 콘티가 모두 생성되면 사용자 개입 없이 영상 단계로 진행.
  useEffect(() => {
    if (!isAutoTrack) return
    if (phase !== "storyboard") return
    if (storyboard.isGenerating || storyboard.error) return
    if (scenes.length === 0 || storyboard.storyboards.length < scenes.length) return
    if (autoStartedRef.current) return
    autoStartedRef.current = true
    toast.info("자동화 트랙: 콘티 완료 → 영상 생성을 자동으로 시작합니다.")
    handleStartVideo()
  }, [
    isAutoTrack,
    phase,
    scenes.length,
    storyboard.isGenerating,
    storyboard.error,
    storyboard.storyboards.length,
    handleStartVideo,
  ])

  function resetToInput() {
    setPhase("input")
    setScenes([])
    setStatuses({})
    autoStartedRef.current = false
  }

  // 영상 완료 시 done 단계로 (파생값 — setState 효과 없이 렌더에서 계산)
  const effectivePhase: Phase =
    phase === "generating" && video.result && !video.isGenerating ? "done" : phase

  const headerSub = useMemo(
    () =>
      ({
        input: "여행지를 입력하고 콘티 생성을 시작하세요",
        storyboard: isAutoTrack
          ? "콘티 생성 후 자동으로 영상 단계로 진행됩니다"
          : "생성된 콘티를 검토하고 승인하세요",
        generating: "영상을 생성하는 중입니다",
        done: "영상이 완성되었습니다",
      })[effectivePhase],
    [effectivePhase, isAutoTrack],
  )

  return (
    <div className="flex h-full flex-col overflow-auto">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold text-foreground">영상 자동 제작</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">{headerSub}</p>
        </div>
        {effectivePhase !== "input" && (
          <Button variant="outline" size="sm" onClick={resetToInput}>
            <ArrowLeft className="h-4 w-4" />
            처음으로
          </Button>
        )}
      </div>

      <div className="container mx-auto w-full max-w-5xl px-6 py-8">
        {effectivePhase === "input" && (
          <div className="mx-auto flex max-w-md flex-col gap-5 rounded-xl border border-border bg-card p-6">
            {channel && (
              <div className="flex items-center justify-between rounded-lg border border-border/60 bg-background/40 px-3 py-2 text-xs">
                <span className="text-muted-foreground">채널</span>
                <span className="font-medium text-foreground">
                  {channel.name} · {TRACK_LABELS[channel.stack.track]}
                </span>
              </div>
            )}

            <div className="flex flex-col gap-2">
              <label className="text-xs font-medium text-muted-foreground">여행지 (국가 / 도시)</label>
              <input
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                placeholder="예: 방콕, 태국"
                className="rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground outline-none focus:border-primary/50"
              />
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-xs font-medium text-muted-foreground">영상 길이</label>
              <div className="flex gap-2">
                {DURATION_OPTIONS.map((opt) => (
                  <button
                    key={opt.min}
                    onClick={() => setDurationMin(opt.min)}
                    className={`flex-1 rounded-lg border px-3 py-2 text-xs font-medium transition-all ${
                      durationMin === opt.min
                        ? "border-primary/50 bg-primary/20 text-foreground"
                        : "border-border text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* 모델 + 비용 안내 (채널 스택에서 결정됨) */}
            <div className="flex flex-col gap-2 rounded-lg border border-border/60 bg-background/40 p-3">
              <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <DollarSign className="h-3.5 w-3.5 text-emerald-400" />
                예상 비용
              </div>
              <CostRow
                label="콘티"
                model={modelLabel(STORYBOARD_MODELS, storyboardModel)}
                detail={`${sceneCount}장 × $${storyboardCost(storyboardModel, 1).toFixed(2)}`}
                cost={contiCost}
              />
              <CostRow
                label="영상"
                model={modelLabel(VIDEO_MODELS, videoModel)}
                detail={videoEst > 0 ? `${totalSeconds}초 추정` : "추정 단가 없음"}
                cost={videoEst}
              />
              {!channel && (
                <p className="mt-0.5 text-[10px] text-muted-foreground">
                  채널을 통해 진입하면 채널 스택의 모델/트랙 설정이 적용됩니다.
                </p>
              )}
            </div>

            <Button className="mt-1" disabled={preparingScenario} onClick={handleStartStoryboard}>
              <Wand2 className="h-4 w-4" />
              {preparingScenario ? "시나리오 생성 중…" : "콘티 생성"}
            </Button>
          </div>
        )}

        {effectivePhase === "storyboard" && (
          <>
            {storyboard.error && (
              <div className="mb-4 flex items-center gap-2 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-xs text-red-400">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                {storyboard.error}
              </div>
            )}
            {storyboard.isGenerating ? (
              <ProgressTracker
                jobStatus={storyboard.job}
                title={`콘티 생성 중 · ${modelLabel(STORYBOARD_MODELS, storyboardModel)} · 예상 $${contiCost.toFixed(2)}`}
              />
            ) : isAutoTrack ? (
              <ProgressTracker
                jobStatus={storyboard.job}
                title="콘티 완료 — 영상 단계로 자동 진행 중"
              />
            ) : (
              <StoryboardReview
                scenes={scenes}
                storyboards={storyboard.storyboards}
                statuses={statuses}
                onApprove={handleApprove}
                onRegenerate={handleRegenerate}
                onStartVideo={handleStartVideo}
              />
            )}
          </>
        )}

        {effectivePhase === "generating" && (
          <>
            {video.error && (
              <div className="mb-4 flex items-center gap-2 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-xs text-red-400">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                {video.error}
              </div>
            )}
            <ProgressTracker
              jobStatus={video.job}
              title={`영상 생성 중 · ${modelLabel(VIDEO_MODELS, videoModel)}`}
            />
          </>
        )}

        {effectivePhase === "done" && (
          <ResultViewer
            result={video.result}
            onRestart={() => {
              resetToInput()
              setCountry("")
            }}
          />
        )}
      </div>
    </div>
  )
}

function CostRow({
  label,
  model,
  detail,
  cost,
}: {
  label: string
  model: string
  detail: string
  cost: number
}) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs">
      <div className="min-w-0">
        <span className="text-muted-foreground">{label}</span>
        <span className="ml-1.5 truncate text-foreground/80">{model}</span>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <span className="text-[10px] text-muted-foreground">{detail}</span>
        <span className="font-semibold text-foreground" style={{ fontFamily: "var(--font-geist-mono)" }}>
          ${cost.toFixed(2)}
        </span>
      </div>
    </div>
  )
}
