"use client"

import { useState } from "react"
import { CheckCircle2, RefreshCw, Pencil, ImageOff, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { Scene, Storyboard } from "@/lib/api"

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"

export type SceneStatus = "pending" | "approved" | "regenerating"

// 백엔드가 주는 image_url(절대 URL) 우선. 없으면 image_path(서버 파일경로)를
// /static 마운트 기준 URL로 변환한다. 백엔드는 output/ 를 /static 으로 서빙한다.
function resolveImageSrc(sb?: Storyboard): string | null {
  if (!sb) return null
  if (sb.image_url) return String(sb.image_url)
  if (sb.image_path) {
    const norm = String(sb.image_path).replace(/\\/g, "/")
    const idx = norm.lastIndexOf("/output/")
    const rel =
      idx >= 0
        ? norm.slice(idx + "/output/".length)
        : norm.replace(/^output\//, "").replace(/^\/+/, "")
    return `${API_BASE}/static/${rel}`
  }
  return null
}

export function SceneCard({
  scene,
  storyboard,
  status,
  onApprove,
  onRegenerate,
  onEdit,
}: {
  scene: Scene
  storyboard?: Storyboard
  status: SceneStatus
  onApprove: () => void
  onRegenerate: (extraInstructions?: string) => void
  onEdit?: (prompt: string) => void
}) {
  const sceneLabel = `S${String(scene.scene_id).padStart(2, "0")}`
  const sceneTitle = scene.location || scene.description || sceneLabel
  const sceneDesc = scene.description || scene.narration || ""
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(String(storyboard?.prompt ?? sceneDesc))
  const [imgError, setImgError] = useState(false)
  const src = resolveImageSrc(storyboard)
  const approved = status === "approved"
  const regenerating = status === "regenerating"

  return (
    <div
      className={`flex flex-col overflow-hidden rounded-xl border bg-card transition-colors ${
        approved ? "border-emerald-500/50" : "border-border"
      }`}
    >
      {/* 이미지 영역 */}
      <div className="relative aspect-video w-full bg-secondary/40">
        {src && !imgError ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={src}
            alt={sceneTitle}
            className="h-full w-full object-cover"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-1.5 text-muted-foreground/60">
            <ImageOff className="h-6 w-6" />
            <span className="text-[10px]">이미지 미리보기 없음</span>
          </div>
        )}

        {regenerating && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/70 backdrop-blur-sm">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
          </div>
        )}

        {approved && (
          <span className="absolute right-2 top-2 flex items-center gap-1 rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
            <CheckCircle2 className="h-3 w-3" /> 승인됨
          </span>
        )}
      </div>

      {/* 본문 */}
      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="flex items-center gap-2">
          <span
            className="text-xs font-bold text-muted-foreground"
            style={{ fontFamily: "var(--font-geist-mono)" }}
          >
            {sceneLabel}
          </span>
          <p className="truncate text-xs font-medium text-foreground">{sceneTitle}</p>
        </div>

        {editing ? (
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={3}
            className="w-full resize-none rounded-md border border-border bg-background px-2 py-1.5 text-xs text-foreground outline-none focus:border-primary/50"
          />
        ) : (
          // 영어 AI 프롬프트(storyboard.prompt)는 UI에서 숨기고 한국어 설명만 표시.
          // 백엔드 프롬프트와 편집 textarea(draft)에는 그대로 유지된다.
          sceneDesc && (
            <p className="line-clamp-2 text-[11px] text-muted-foreground">
              {sceneDesc}
            </p>
          )
        )}

        {/* 액션 버튼 */}
        <div className="mt-auto flex flex-wrap gap-1.5 pt-1">
          {editing ? (
            <>
              <Button
                size="sm"
                className="flex-1"
                disabled={regenerating}
                onClick={() => {
                  onEdit?.(draft)
                  onRegenerate(draft)
                  setEditing(false)
                }}
              >
                적용 후 재생성
              </Button>
              <Button size="sm" variant="outline" onClick={() => setEditing(false)}>
                취소
              </Button>
            </>
          ) : (
            <>
              <Button
                size="sm"
                variant={approved ? "secondary" : "default"}
                className="flex-1"
                disabled={regenerating}
                onClick={onApprove}
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                {approved ? "승인 취소" : "승인"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={regenerating}
                onClick={() => onRegenerate()}
                title="재생성"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${regenerating ? "animate-spin" : ""}`} />
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={regenerating}
                onClick={() => setEditing(true)}
                title="프롬프트 수정"
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
