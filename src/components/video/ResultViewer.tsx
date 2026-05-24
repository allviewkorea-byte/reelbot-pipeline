"use client"

import { Download, Plus, CheckCircle2, FileVideo } from "lucide-react"
import { Button } from "@/components/ui/button"

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"

function resolveSrc(pathOrUrl?: string | null): string | null {
  if (!pathOrUrl) return null
  if (/^https?:\/\//.test(pathOrUrl)) return pathOrUrl
  return `${API_BASE}/${pathOrUrl.replace(/^\/+/, "")}`
}

export function ResultViewer({
  result,
  onRestart,
}: {
  result: Record<string, unknown> | null
  onRestart: () => void
}) {
  const videoPath =
    (result?.video_url as string) ??
    (result?.video_path as string) ??
    (result?.output_path as string) ??
    null
  const src = resolveSrc(videoPath)

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-emerald-400">
        <CheckCircle2 className="h-5 w-5" />
        영상 생성 완료
      </div>

      <div className="overflow-hidden rounded-xl border border-border bg-card">
        {src ? (
          <video src={src} controls className="aspect-video w-full bg-black" />
        ) : (
          <div className="flex aspect-video w-full flex-col items-center justify-center gap-2 text-muted-foreground">
            <FileVideo className="h-8 w-8" />
            <span className="text-xs">영상이 생성되었지만 미리보기 경로를 찾지 못했습니다.</span>
            {videoPath && (
              <code className="rounded bg-secondary px-2 py-1 text-[10px]">{videoPath}</code>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between">
        <Button variant="outline" onClick={onRestart}>
          <Plus className="h-4 w-4" />
          새 영상 만들기
        </Button>
        {src && (
          <Button asChild>
            <a href={src} download>
              <Download className="h-4 w-4" />
              다운로드
            </a>
          </Button>
        )}
      </div>
    </div>
  )
}
