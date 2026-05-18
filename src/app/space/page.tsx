"use client"

import { useState, useRef } from "react"
import {
  Upload,
  Video,
  ImageIcon,
  CheckCircle2,
  Loader2,
  Clock,
  Lightbulb,
  Film,
} from "lucide-react"

// ── Types ─────────────────────────────────────────────────────────
interface SpaceItem {
  id: number
  name: string
  format: string
  meta: string
  date: string
  status: "done" | "running" | "waiting"
  type: "video" | "image"
}

// ── Mock uploads ──────────────────────────────────────────────────
const UPLOADS_INIT: SpaceItem[] = [
  {
    id: 1,
    name: "카오산 로드 식당 영상",
    format: "MP4",
    meta: "32초",
    date: "2025-05-17",
    status: "done" as const,
    type: "video" as const,
  },
  {
    id: 2,
    name: "왓포 사원 입구 사진",
    format: "JPG",
    meta: "4.2 MB",
    date: "2025-05-17",
    status: "running" as const,
    type: "image" as const,
  },
  {
    id: 3,
    name: "시부야 횡단보도 영상",
    format: "MP4",
    meta: "18초",
    date: "2025-05-16",
    status: "waiting" as const,
    type: "video" as const,
  },
]

const GUIDE_ITEMS = [
  "AI 캐릭터가 실제 공간에서 활동하는 영상 생성",
  "협업 식당·가게 홍보 콘텐츠로도 활용 가능",
  "영상 안정성을 위해 핸드폰 가로 촬영 권장",
]

// ── Status badge ──────────────────────────────────────────────────
function StatusBadge({ status }: { status: "done" | "running" | "waiting" }) {
  if (status === "done")
    return (
      <span className="flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
        <CheckCircle2 className="h-2.5 w-2.5" /> 합성 완료
      </span>
    )
  if (status === "running")
    return (
      <span className="flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-400">
        <Loader2 className="h-2.5 w-2.5 animate-spin" /> 합성 중
      </span>
    )
  return (
    <span className="flex items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
      <Clock className="h-2.5 w-2.5" /> 대기
    </span>
  )
}

// ── Page ──────────────────────────────────────────────────────────
export default function SpacePage() {
  const [uploads, setUploads] = useState<SpaceItem[]>(UPLOADS_INIT)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const files = Array.from(e.dataTransfer.files)
    addFiles(files)
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    addFiles(files)
  }

  function addFiles(files: File[]) {
    const newItems: SpaceItem[] = files.map((f, i) => {
      const isVideo = f.type.startsWith("video/")
      return {
        id: Date.now() + i,
        name: f.name.replace(/\.[^.]+$/, ""),
        format: f.name.split(".").pop()?.toUpperCase() ?? "FILE",
        meta: isVideo ? "—초" : `${(f.size / 1024 / 1024).toFixed(1)} MB`,
        date: new Date().toISOString().slice(0, 10),
        status: "waiting" as const,
        type: (isVideo ? "video" : "image") as "video" | "image",
      }
    })
    setUploads((prev) => [...newItems, ...prev])
  }

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-auto p-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-foreground">실제 공간 업로드</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          직접 촬영한 영상/사진에 AI 캐릭터를 합성합니다
        </p>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed py-12 transition-all ${
          dragging
            ? "border-primary bg-primary/5"
            : "border-border bg-card hover:border-primary/40 hover:bg-primary/5"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept="video/mp4,video/quicktime,image/jpeg,image/png"
          multiple
          className="hidden"
          onChange={handleFileInput}
        />
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10 border border-primary/20">
          <Upload className={`h-7 w-7 transition-colors ${dragging ? "text-primary" : "text-primary/60"}`} />
        </div>
        <div className="text-center">
          <p className="text-sm font-medium text-foreground">
            영상 또는 사진을 드래그하거나 클릭
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            지원 형식: MP4, MOV, JPG, PNG
          </p>
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); inputRef.current?.click() }}
          className="rounded-lg border border-border bg-background px-4 py-2 text-xs font-medium text-foreground transition-colors hover:bg-secondary/40"
        >
          파일 선택
        </button>
      </div>

      {/* Uploaded files grid */}
      {uploads.length > 0 && (
        <div>
          <h2 className="mb-3 text-sm font-semibold text-foreground">업로드된 공간</h2>
          <div className="grid grid-cols-2 gap-3">
            {uploads.map((item) => (
              <div
                key={item.id}
                className="rounded-xl border border-border bg-card overflow-hidden transition-colors hover:border-border/80"
              >
                {/* Thumbnail */}
                <div className="flex h-28 items-center justify-center bg-secondary/40">
                  {item.type === "video" ? (
                    <Film className="h-10 w-10 text-muted-foreground/40" />
                  ) : (
                    <ImageIcon className="h-10 w-10 text-muted-foreground/40" />
                  )}
                </div>

                {/* Info */}
                <div className="p-3">
                  <p className="truncate text-xs font-semibold text-foreground">{item.name}</p>
                  <div className="mt-1 flex items-center justify-between">
                    <span className="text-[11px] text-muted-foreground">
                      {item.format} · {item.meta}
                    </span>
                    <StatusBadge status={item.status} />
                  </div>
                  <p className="mt-1 text-[10px] text-muted-foreground/60">{item.date}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Guide card */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="mb-3 flex items-center gap-2">
          <Lightbulb className="h-4 w-4 text-amber-400" />
          <h2 className="text-sm font-semibold text-foreground">활용 가이드</h2>
        </div>
        <ul className="flex flex-col gap-2">
          {GUIDE_ITEMS.map((item, i) => (
            <li key={i} className="flex items-start gap-2 text-xs text-muted-foreground">
              <Video className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary/60" />
              {item}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
