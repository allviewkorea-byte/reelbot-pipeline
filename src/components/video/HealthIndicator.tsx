"use client"

import { useHealthCheck } from "@/hooks/useHealthCheck"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"

// 사이드바 등에 들어가는 백엔드 연결 상태 dot.
export function HealthIndicator() {
  const state = useHealthCheck(5000)

  const config = {
    checking: { dot: "bg-amber-400 animate-pulse", label: "백엔드 확인 중…" },
    online: { dot: "bg-emerald-500", label: "백엔드 연결됨" },
    offline: {
      dot: "bg-red-500",
      label: "백엔드 서버가 응답하지 않습니다. 서버가 실행 중인지 확인해주세요.",
    },
  }[state]

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-muted-foreground">
            <span className={`h-2 w-2 shrink-0 rounded-full ${config.dot}`} />
            <span className="truncate">
              {state === "online"
                ? "백엔드 연결됨"
                : state === "offline"
                  ? "백엔드 연결 끊김"
                  : "확인 중…"}
            </span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[220px] text-xs">
          {config.label}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
