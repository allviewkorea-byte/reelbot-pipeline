import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"

// 운동 채널 [AI 이미지 생성](PR-1) — FastAPI POST /music/queue/{mixId}/ai-image (비동기 job_id 반환).
// 진행 상태는 재렌더와 같은 /api/music/queue/rerender/status/{jobId} 로 폴링한다.
export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ mixId: string }> },
) {
  const { mixId } = await params
  return proxyJson(`/music/queue/${encodeURIComponent(mixId)}/ai-image`, { method: "POST" })
}
