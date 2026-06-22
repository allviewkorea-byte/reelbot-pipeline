// 곡 구간 계산 — 현재 시각 t(초)가 속한 곡과 그 구간 경계를 돌려준다.
export interface Track {
  title: string;
  start_sec: number;
}

export interface ActiveTrack {
  title: string;
  start: number;
  end: number;
}

// t(초)에 표시할 곡을 찾는다. 다음 곡 시작 = 현재 곡 끝, 마지막 곡은 durationSec 까지.
// 제목이 빈 곡은 표시하지 않는다(null).
export function currentTrack(
  tracks: Track[],
  t: number,
  durationSec: number,
): ActiveTrack | null {
  for (let i = 0; i < tracks.length; i++) {
    const start = tracks[i].start_sec || 0;
    const end =
      i + 1 < tracks.length ? tracks[i + 1].start_sec || durationSec : durationSec;
    if (t >= start && t < end) {
      const title = (tracks[i].title || "").trim();
      return title ? { title, start, end } : null;
    }
  }
  return null;
}
