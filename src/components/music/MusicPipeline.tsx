"use client"

// 음악 파이프라인 시각화 — 주제 → 음원 → 가사 → 영상 → 업로드 → 유튜브.
// 백곰 PipelineNodeGraph 패턴 차용(직접 import 금지). 라운드 박스 노드 + 흐르는 연결선.
// keyframes 는 styled-jsx(컴포넌트 스코프) — globals 금지 규칙 준수. 디자인 토큰만 사용.
import { Music2, FileAudio, PenLine, Clapperboard, UploadCloud, MonitorPlay } from "lucide-react"

const STAGES = [
  { key: "theme", label: "주제", Icon: Music2 },
  { key: "audio", label: "음원", Icon: FileAudio },
  { key: "lyrics", label: "가사", Icon: PenLine },
  { key: "video", label: "영상", Icon: Clapperboard },
  { key: "upload", label: "업로드", Icon: UploadCloud },
  { key: "youtube", label: "유튜브", Icon: MonitorPlay },
] as const

export function MusicPipeline() {
  return (
    <div className="flex items-center gap-1 overflow-x-auto py-1">
      {STAGES.map(({ key, label, Icon }, i) => (
        <div key={key} className="flex shrink-0 items-center gap-1">
          <div className="flex shrink-0 flex-col items-center gap-1.5">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-border bg-secondary/30 text-primary">
              <Icon className="h-5 w-5" />
            </div>
            <span className="text-[11px] font-medium text-muted-foreground">{label}</span>
          </div>
          {i < STAGES.length - 1 && (
            <div className="m-flow relative mx-0.5 h-0.5 w-6 shrink-0 overflow-hidden rounded-full bg-secondary/50 sm:w-10">
              <span className="m-flow-bar absolute inset-y-0 left-0 w-1/2 rounded-full bg-primary/70" />
            </div>
          )}
        </div>
      ))}
      <style jsx>{`
        .m-flow-bar {
          animation: m-flow 2.2s linear infinite;
        }
        @keyframes m-flow {
          0% {
            transform: translateX(-100%);
          }
          100% {
            transform: translateX(220%);
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .m-flow-bar {
            animation: none;
          }
        }
      `}</style>
    </div>
  )
}
