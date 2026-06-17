import { NextRequest } from "next/server"
import { proxyJson } from "@/lib/proxy"
import { getChannelStatus } from "@/lib/supabase"
import { BAEKGOM_CHANNEL_ID } from "@/lib/content-plan"
import { modeToPrivacy } from "@/lib/channel-status"

// 사연 end-to-end 생성은 백그라운드 job 이라 job_id 를 즉시 반환한다(QUICK).
// 실제 진행은 /api/jobs/{id}/status 폴링으로 추적한다.
//
// 업로드 공개/비공개는 채널 모드(channel_status.mode)로 결정한다: auto=public, semi=private.
// sayeon/page.tsx(보호 대상)는 수정하지 않고, 여기(프록시)에서 privacy 를 주입한다.
// 본문에 privacy 가 이미 있으면 존중하고, 없을 때만 모드로 채운다. 조회 실패는 무시(백엔드
// env 폴백). YOUTUBE_AUTO_PUBLISH 게이트(업로드 여부)는 백엔드 env 그대로 — 여기선 안 건드림.
export async function POST(request: NextRequest) {
  const body = await request.json()
  // privacy(공개/비공개) + synthetic_media(AI 표시)를 채널 토글에서 주입(둘 다 미지정 시).
  // 본문에 이미 있으면 존중(예: 테스트 영상 privacy='private'). 조회 실패는 무시(백엔드 env 폴백).
  if (body && typeof body === "object" && (body.privacy == null || body.synthetic_media == null)) {
    try {
      const { mode, syntheticMedia } = await getChannelStatus(BAEKGOM_CHANNEL_ID)
      if (body.privacy == null) body.privacy = modeToPrivacy(mode)
      if (body.synthetic_media == null) body.synthetic_media = syntheticMedia
    } catch {
      /* 조회 실패 → 미주입(백엔드 YOUTUBE_PRIVACY_STATUS / YOUTUBE_SYNTHETIC_MEDIA 폴백) */
    }
  }
  return proxyJson("/sayeon/generate", { method: "POST", body })
}
