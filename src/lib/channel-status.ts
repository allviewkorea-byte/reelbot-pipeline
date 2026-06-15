// 채널 가동 상태(ON/OFF) 공유 상수. React 의존 없음 — 서버/클라이언트 양쪽에서 import.
//
// "가동 중" = 채널 자동 운영 ON. 지금 PR 은 이 상태를 켜고/끄고/저장/표시까지만 한다.
// 실제 자동 업로드(스케줄러가 이 상태를 보고 동작)는 후속 큰 작업.

// 같은 탭 내 클라이언트 컴포넌트(대시보드 토글 ↔ 사이드바 표시) 즉시 동기화용 이벤트명.
export const CHANNEL_STATUS_EVENT = "reelbot:channel-status-changed"

export interface ChannelStatusDetail {
  channelId: string
  isActive: boolean
}

// 업로드 모드 — auto=유튜브 공개, semi(반자동)=유튜브 비공개. 기본 semi(안전).
export type ChannelMode = "auto" | "semi"

export function modeToPrivacy(mode: ChannelMode): "public" | "private" {
  return mode === "auto" ? "public" : "private"
}
