import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { useAudioData, visualizeAudio } from "@remotion/media-utils";
import { moodColors } from "./colors";
import { currentTrack, Track } from "./tracks";

// Composition Props 제약(Record<string, unknown>)을 만족하려면 interface 가 아닌 type 별칭이어야 한다.
export type MusicVizProps = {
  tracks: Track[];
  mood: string;
  durationSec: number;
};

// 자산은 render.mjs 가 publicDir 로 복사한 고정 이름을 staticFile 로 참조한다.
const AUDIO = "audio.mp3";
const BG = "bg.png";

const BARS = 48;
const NUM_SAMPLES = 256; // visualizeAudio 는 2의 거듭제곱 필요.
const SMOOTH_FRAMES = 4; // 최근 N프레임 평균 → 부드러운 감쇠(차분).

export const MusicViz: React.FC<MusicVizProps> = ({ tracks, mood, durationSec }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const audioData = useAudioData(staticFile(AUDIO));
  const [c1, c2] = moodColors(mood);

  // ── 이퀄 막대 진폭(최근 프레임 평균으로 감쇠) ──────────────────────
  const values: number[] = new Array(BARS).fill(0);
  if (audioData) {
    const windows = [];
    for (let d = 0; d < SMOOTH_FRAMES; d++) {
      windows.push(
        visualizeAudio({
          audioData,
          frame: Math.max(0, frame - d),
          fps,
          numberOfSamples: NUM_SAMPLES,
        }),
      );
    }
    for (let i = 0; i < BARS; i++) {
      // 저~중역(에너지 많은 구간)을 펼쳐 매핑.
      const idx = 1 + Math.round((i / (BARS - 1)) * (NUM_SAMPLES * 0.45));
      let sum = 0;
      for (const w of windows) sum += w[idx] || 0;
      values[i] = sum / windows.length;
    }
  }

  // ── 레이아웃: 맨 아래 얇은 띠(높이 ~12%), 가로 66% 중앙 ──────────
  const bandWidth = width * 0.66;
  const left = (width - bandWidth) / 2;
  const slot = bandWidth / BARS;
  const barW = slot * 0.5; // 굵은 막대
  const maxBarH = height * 0.12; // 띠 높이 ~12%
  const baseBottom = height * 0.035; // 화면 맨 아래에서 살짝 띄움

  // ── 곡 제목(구간별, 경계 페이드) ─────────────────────────────────
  const t = frame / fps;
  const active = currentTrack(tracks, t, durationSec);
  let titleOpacity = 0;
  if (active) {
    const fadeFrames = Math.round(fps * 0.6);
    const sf = active.start * fps;
    const ef = active.end * fps;
    titleOpacity = Math.min(
      interpolate(frame, [sf, sf + fadeFrames], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      }),
      interpolate(frame, [ef - fadeFrames, ef], [1, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      }),
    );
  }

  // 제목은 이퀄 위, 그 위가 자막 자리(#6b 후속). 썸네일 상단(PLAY LIST·인물)과 겹치지 않게 하단에.
  const titleBottom = baseBottom + maxBarH + 56;

  return (
    <AbsoluteFill>
      {/* 1) 배경 썸네일(정지, PLAY LIST·인물 포함 — 대표 제작) */}
      <Img src={staticFile(BG)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />

      {/* 오디오 트랙(영상에 믹스 mp3 포함) */}
      <Audio src={staticFile(AUDIO)} />

      {/* 2) 자막 자리 — 곡 제목과 이퀄 사이(이번엔 비움) */}

      {/* 3) 곡 구간별 제목(하단, 페이드) */}
      {active ? (
        <div
          style={{
            position: "absolute",
            bottom: titleBottom,
            width: "100%",
            textAlign: "center",
            opacity: titleOpacity,
            color: "white",
            fontSize: 46,
            fontWeight: 700,
            fontFamily: "sans-serif",
            letterSpacing: 0.5,
            textShadow: "0 2px 12px rgba(0,0,0,0.75)",
          }}
        >
          {active.title}
        </div>
      ) : null}

      {/* 4) 맨 아래 굵은 둥근 바 이퀄(반투명·감쇠) */}
      {values.map((v, i) => {
        // 고역 롤오프 보정(tilt): 실제 음악은 고역 에너지가 약해 우측 막대가 죽기 쉽다.
        // 막대 인덱스가 커질수록 게인을 키워(최대 ~2.6배) 전 대역이 고르게 반응하게 한다.
        const tilt = 1 + (i / (BARS - 1)) * 1.6;
        const amp = Math.min(1, v * 2.4 * tilt);
        const h = 10 + amp * maxBarH;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              bottom: baseBottom,
              left: left + i * slot + (slot - barW) / 2,
              width: barW,
              height: h,
              borderRadius: barW, // 끝이 둥근 막대
              opacity: 0.72, // 반투명 — 배경 안 가림
              background: `linear-gradient(to top, ${c1}, ${c2})`,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};
