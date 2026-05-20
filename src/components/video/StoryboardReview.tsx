"use client"

import { Play } from "lucide-react"
import { Button } from "@/components/ui/button"
import { SceneCard, type SceneStatus } from "./SceneCard"
import type { Scene, Storyboard } from "@/lib/api"

export function StoryboardReview({
  scenes,
  storyboards,
  statuses,
  onApprove,
  onRegenerate,
  onEdit,
  onStartVideo,
}: {
  scenes: Scene[]
  storyboards: Storyboard[]
  statuses: Record<string, SceneStatus>
  onApprove: (sceneId: string) => void
  onRegenerate: (sceneId: string, extraInstructions?: string) => void
  onEdit?: (sceneId: string, prompt: string) => void
  onStartVideo: () => void
}) {
  const findStoryboard = (sceneId: string, idx: number): Storyboard | undefined =>
    storyboards.find((s) => String(s.scene_id) === sceneId) ?? storyboards[idx]

  const approvedCount = scenes.filter(
    (s) => statuses[String(s.scene_id)] === "approved",
  ).length
  const allApproved = scenes.length > 0 && approvedCount === scenes.length

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-foreground">콘티 검토</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            각 씬을 확인하고 승인하세요. 모든 씬을 승인하면 영상 생성을 시작할 수 있습니다.
          </p>
        </div>
        <span
          className="text-sm font-bold text-foreground"
          style={{ fontFamily: "var(--font-geist-mono)" }}
        >
          {approvedCount} / {scenes.length}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {scenes.map((scene, idx) => {
          const sid = String(scene.scene_id)
          return (
            <SceneCard
              key={sid}
              scene={scene}
              storyboard={findStoryboard(sid, idx)}
              status={statuses[sid] ?? "pending"}
              onApprove={() => onApprove(sid)}
              onRegenerate={(extra) => onRegenerate(sid, extra)}
              onEdit={onEdit ? (prompt) => onEdit(sid, prompt) : undefined}
            />
          )
        })}
      </div>

      <div className="flex items-center justify-end gap-3 border-t border-border pt-4">
        {!allApproved && (
          <span className="text-xs text-muted-foreground">
            모든 씬을 승인하면 영상 생성이 활성화됩니다.
          </span>
        )}
        <Button disabled={!allApproved} onClick={onStartVideo}>
          <Play className="h-4 w-4 fill-current" />
          영상 생성 시작
        </Button>
      </div>
    </div>
  )
}
