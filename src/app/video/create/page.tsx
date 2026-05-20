"use client"

import { useCallback, useMemo, useState } from "react"
import { Wand2, AlertTriangle, ArrowLeft } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { useStoryboard } from "@/hooks/useStoryboard"
import { useVideoGeneration } from "@/hooks/useVideoGeneration"
import { generateScenario, type Scene } from "@/lib/api"
import { StoryboardReview } from "@/components/video/StoryboardReview"
import { ProgressTracker } from "@/components/video/ProgressTracker"
import { ResultViewer } from "@/components/video/ResultViewer"
import type { SceneStatus } from "@/components/video/SceneCard"

type Phase = "input" | "storyboard" | "generating" | "done"

const DURATION_OPTIONS = [
  { label: "1분 (6씬)", min: 1 },
  { label: "2분 (12씬)", min: 2 },
  { label: "4분 (24씬)", min: 4 },
]

// Phase 3 대비 — UI placeholder (동작 없음)
const MODEL_OPTIONS = ["Kling v1", "Kling v2.6", "Kling v3.0"]

export default function VideoCreatePage() {
  const [phase, setPhase] = useState<Phase>("input")
  const [country, setCountry] = useState("")
  const [durationMin, setDurationMin] = useState(2)
  const [preparingScenario, setPreparingScenario] = useState(false)

  const [scenes, setScenes] = useState<Scene[]>([])
  const [statuses, setStatuses] = useState<Record<string, SceneStatus>>({})

  const storyboard = useStoryboard()
  const video = useVideoGeneration()

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
      await storyboard.generate({ scenario: res.scenario ?? "", scenes: sc })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "콘티 생성에 실패했습니다.")
    } finally {
      setPreparingScenario(false)
    }
  }, [country, durationMin, storyboard])

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
      })
      setStatuses((prev) => ({ ...prev, [sceneId]: "pending" }))
      toast.success(`${sceneId} 재생성 완료`)
    },
    [scenes, storyboard],
  )

  const handleStartVideo = useCallback(async () => {
    setPhase("generating")
    await video.start({
      job_id: storyboard.job?.job_id ?? "",
      scenes: scenes as unknown as Record<string, unknown>[],
      approved_storyboards: storyboard.storyboards,
      scenario_mode: "B",
      seedance_mode: "kie",
    })
  }, [scenes, storyboard, video])

  // 영상 완료 시 done 단계로 (파생값 — setState 효과 없이 렌더에서 계산)
  const effectivePhase: Phase =
    phase === "generating" && video.result && !video.isGenerating ? "done" : phase

  const headerSub = useMemo(
    () =>
      ({
        input: "여행지를 입력하고 콘티 생성을 시작하세요",
        storyboard: "생성된 콘티를 검토하고 승인하세요",
        generating: "영상을 생성하는 중입니다",
        done: "영상이 완성되었습니다",
      })[effectivePhase],
    [effectivePhase],
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
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setPhase("input")
              setScenes([])
              setStatuses({})
            }}
          >
            <ArrowLeft className="h-4 w-4" />
            처음으로
          </Button>
        )}
      </div>

      <div className="container mx-auto w-full max-w-5xl px-6 py-8">
        {effectivePhase === "input" && (
          <div className="mx-auto flex max-w-md flex-col gap-5 rounded-xl border border-border bg-card p-6">
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

            {/* Phase 3 대비 placeholder — 동작 없음 */}
            <div className="flex flex-col gap-2 opacity-60">
              <label className="text-xs font-medium text-muted-foreground">
                영상 모델 <span className="text-[10px]">(준비 중)</span>
              </label>
              <select
                disabled
                className="cursor-not-allowed rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-muted-foreground"
              >
                {MODEL_OPTIONS.map((m) => (
                  <option key={m}>{m}</option>
                ))}
              </select>
            </div>

            <Button
              className="mt-1"
              disabled={preparingScenario}
              onClick={handleStartStoryboard}
            >
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
              <ProgressTracker jobStatus={storyboard.job} title="콘티 생성 중" />
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
            <ProgressTracker jobStatus={video.job} title="영상 생성 중" />
          </>
        )}

        {effectivePhase === "done" && (
          <ResultViewer
            result={video.result}
            onRestart={() => {
              setPhase("input")
              setScenes([])
              setStatuses({})
              setCountry("")
            }}
          />
        )}
      </div>
    </div>
  )
}
