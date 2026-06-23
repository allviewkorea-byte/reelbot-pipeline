import {
  AbsoluteFill,
  Audio,
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { useAudioData, visualizeAudio } from "@remotion/media-utils";
import { loadFont as loadPlayfair } from "@remotion/google-fonts/PlayfairDisplay";
import { loadFont as loadDancing } from "@remotion/google-fonts/DancingScript";
import { loadFont as loadMontserrat } from "@remotion/google-fonts/Montserrat";
import { loadFont as loadPoppins } from "@remotion/google-fonts/Poppins";
import { loadFont as loadBebas } from "@remotion/google-fonts/BebasNeue";
import { loadFont as loadOswald } from "@remotion/google-fonts/Oswald";
import { loadFont as loadAnton } from "@remotion/google-fonts/Anton";
import { loadFont as loadArchivo } from "@remotion/google-fonts/Archivo";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadDMSans } from "@remotion/google-fonts/DMSans";
import { loadFont as loadCormorant } from "@remotion/google-fonts/CormorantGaramond";
import { moodColors } from "./colors";
import { currentTrack, Track } from "./tracks";

// Google Fonts(무료, OFL) — Playfair Display(세리프: PLAY LIST·부제), Dancing Script(필기: 곡 제목).
const playfair = loadPlayfair();
const dancing = loadDancing();
const SERIF = playfair.fontFamily;
const SCRIPT = dancing.fontFamily;

// #35-A 디자인 본부 프리셋 폰트 10종 — UI 드롭다운 이름 → 실제 fontFamily 매핑.
const PRESET_FONTS: Record<string, string> = {
  Montserrat: loadMontserrat().fontFamily,
  Poppins: loadPoppins().fontFamily,
  "Bebas Neue": loadBebas().fontFamily,
  Oswald: loadOswald().fontFamily,
  Anton: loadAnton().fontFamily,
  Archivo: loadArchivo().fontFamily,
  Inter: loadInter().fontFamily,
  "DM Sans": loadDMSans().fontFamily,
  "Playfair Display": playfair.fontFamily,
  "Cormorant Garamond": loadCormorant().fontFamily,
};

// #35-A 디자인 설정(채널 설정 본부에서 저장). 비어 있으면 현재 하드코딩값으로 폴백(회귀 0).
type TextStyleCfg = {
  font_family?: string;
  font_size?: number;
  font_weight?: number;
  color?: string;
  opacity?: number;
  italic?: boolean; // #36 title/subtitle 만 사용
  border?: { enabled?: boolean; width?: number; color?: string };
};
export type DesignConfig = {
  play_list?: TextStyleCfg;
  where_label?: TextStyleCfg;
  title?: TextStyleCfg; // #36 곡 제목(좌하단)
  subtitle?: TextStyleCfg; // #36 부제(좌하단)
} | null;

// 테두리(외곽선) — border.enabled 일 때만 -webkit-text-stroke + paint-order(깔끔한 외곽).
function strokeStyle(b?: { enabled?: boolean; width?: number; color?: string }): React.CSSProperties {
  if (!b?.enabled) return {};
  return { WebkitTextStroke: `${b.width ?? 1}px ${b.color ?? "#000000"}`, paintOrder: "stroke fill" };
}

// 곡 분석 결과(#20·#27). null 이면 mood 기반 색상으로 폴백.
export type VizSpec = {
  primary_color?: string;
  secondary_color?: string;
  text_color?: string; // #27: 무시(텍스트는 항상 흰색). 호환 위해 필드만 유지.
  subtitle_en?: string;
  dominant_emotion?: string;
  scene_keywords?: string[];
  lighting?: string;
  location_en?: string; // #27: WHERE 라벨
  season?: string;
  location_category?: string;
  mood_category?: string;
};

// Composition Props 제약(Record<string, unknown>)을 만족하려면 type 별칭이어야 한다.
export type MusicVizProps = {
  tracks: Track[];
  mood: string;
  durationSec: number;
  vizSpec: VizSpec | null;
  designConfig?: DesignConfig;
};

const AUDIO = "audio.mp3";
const BG = "bg.png";

const BARS = 48;
const NUM_SAMPLES = 256; // visualizeAudio 는 2의 거듭제곱 필요.
const SMOOTH_FRAMES = 2; // #34 활발한 반응 — 평균 윈도우 4→2(빠른 감쇠). 진폭·tilt·캡 불변.

// 인트로 타임라인(초) — A 옵션 확정.
const STATIC_END = 3.5; // 0~3.5 정지(거대 PLAY LIST + 부제 + 곡제목)
const FADE_END = 4.7; // 3.5~4.7 PLAY LIST 좌하단 이동·축소·페이드 + 이퀄 등장
const TYPE_START = 4.9; // 4.9~6.1 타이프라이터 재등장
const TYPE_END = 6.1; // 6.1~ 본 영상

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const easeInOut = Easing.bezier(0.65, 0, 0.35, 1);

export const MusicViz: React.FC<MusicVizProps> = ({ tracks, mood, durationSec, vizSpec, designConfig }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const audioData = useAudioData(staticFile(AUDIO));

  // ── 색상: vizSpec 우선, 없으면 mood 매핑 ──────────────────────────
  const [mc1, mc2] = moodColors(mood);
  const c1 = vizSpec?.primary_color || mc1;
  const c2 = vizSpec?.secondary_color || mc2;
  // #27: 모든 텍스트 순백 고정(vizSpec.text_color 무시). 이퀄·배경 색감만 mood 별 유지.
  const textColor = "#FFFFFF";
  const subtitleEn = (vizSpec?.subtitle_en || "").trim();
  const locationEn = (vizSpec?.location_en || "").trim() || "City View"; // #33: 항상 WHERE 표시(폴백)
  const firstTitle = (tracks[0]?.title || "").trim();

  // ── #35-A 디자인 설정: 미지정 필드는 현재 하드코딩값으로 폴백(designConfig 비면 100% 동일) ──
  const plCfg = designConfig?.play_list ?? {};
  const wlCfg = designConfig?.where_label ?? {};
  const plFontFamily = PRESET_FONTS[plCfg.font_family ?? ""] ?? SERIF;
  const plFontWeight = plCfg.font_weight ?? 700;
  const plColor = plCfg.color ?? textColor;
  const plOpacityMul = plCfg.opacity ?? 1;
  const plFontSize = plCfg.font_size ?? height * 0.3;
  const plStroke = strokeStyle(plCfg.border);
  const wlFontFamily = PRESET_FONTS[wlCfg.font_family ?? ""] ?? "sans-serif";
  const wlFontSize = wlCfg.font_size ?? width * 0.012;
  const wlFontWeight = wlCfg.font_weight ?? 600;
  const wlColor = wlCfg.color ?? "#FFFFFF";
  const wlOpacity = wlCfg.opacity ?? 0.9;
  const wlStroke = strokeStyle(wlCfg.border);

  // ── #36 제목·부제(좌하단 블록): title/subtitle 키 없으면 현재값으로 폴백(기울임 포함 회귀 0) ──
  const tCfg = designConfig?.title;
  const sCfg = designConfig?.subtitle;
  const tFontFamily = tCfg ? (PRESET_FONTS[tCfg.font_family ?? ""] ?? SCRIPT) : SCRIPT;
  const tFontWeight = tCfg?.font_weight; // 미지정이면 undefined → 현재(미설정=400)
  const tColor = tCfg?.color ?? textColor;
  const tFontSize = tCfg?.font_size ?? width * 0.044;
  const tFontStyle = tCfg ? (tCfg.italic ? "italic" : "normal") : undefined; // 현재 미설정
  const tOpacityMul = tCfg?.opacity ?? 1;
  const tStroke = strokeStyle(tCfg?.border);
  const sFontFamily = sCfg ? (PRESET_FONTS[sCfg.font_family ?? ""] ?? SERIF) : SERIF;
  const sFontWeight = sCfg?.font_weight;
  const sColor = sCfg?.color ?? textColor;
  const sFontSize = sCfg?.font_size ?? width * 0.02;
  const sFontStyle = sCfg ? (sCfg.italic ? "italic" : "normal") : "italic"; // 현재 항상 italic
  const sOpacity = sCfg?.opacity ?? 1;
  const sStroke = strokeStyle(sCfg?.border);

  // ── 이퀄 막대 진폭(최근 프레임 평균으로 감쇠) ──────────────────────
  // 오디오 디코드가 안 되는 경우에도 막대가 보이도록 idle 사인으로 폴백(가시성 보장).
  const values: number[] = new Array(BARS).fill(0);
  if (audioData) {
    const windows = [];
    for (let d = 0; d < SMOOTH_FRAMES; d++) {
      windows.push(
        visualizeAudio({ audioData, frame: Math.max(0, frame - d), fps, numberOfSamples: NUM_SAMPLES }),
      );
    }
    for (let i = 0; i < BARS; i++) {
      const idx = 1 + Math.round((i / (BARS - 1)) * (NUM_SAMPLES * 0.45));
      let sum = 0;
      for (const w of windows) sum += w[idx] || 0;
      values[i] = sum / windows.length;
    }
  } else {
    for (let i = 0; i < BARS; i++) {
      values[i] = 0.22 + 0.16 * (0.5 + 0.5 * Math.sin(frame / 6 + i * 0.5));
    }
  }

  // ── 레이아웃 ──────────────────────────────────────────────────────
  const bandWidth = width * 0.66;
  const left = (width - bandWidth) / 2;
  const slot = bandWidth / BARS;
  const barW = slot * 0.5;
  const maxBarH = height * 0.12;
  const baseBottom = height * 0.035;

  // ── 인트로: 부제/곡제목 정지 표시 페이드(0~4.7) ───────────────────
  const introOpacity = interpolate(frame, [STATIC_END * fps, FADE_END * fps], [1, 0], clamp);

  // ── 이퀄 등장(3.5초부터 아래에서 상승, 4.7초 완전 등장 후 유지) ────
  const eqIn = interpolate(frame, [STATIC_END * fps, FADE_END * fps], [0, 1], clamp);
  const eqTranslateY = (1 - eqIn) * (maxBarH + baseBottom + 60);

  // ── PLAY LIST: 0~3.5 중앙상단 거대 → 3.5~4.7 좌하단 이동·축소·페이드 ──
  const LARGE = plFontSize; // 폰트 높이 ~30%(기본) — #35-A 설정 시 그 px. 인트로 도킹 비율은 불변.
  const plProgress = interpolate(frame, [STATIC_END * fps, FADE_END * fps], [0, 1], {
    ...clamp,
    easing: easeInOut,
  });
  const plScale = interpolate(plProgress, [0, 1], [1, (height * 0.05) / LARGE]); // 끝 ~5% 높이
  const plX = interpolate(plProgress, [0, 1], [width * 0.5, width * 0.22]); // 중앙 → 좌
  const plY = interpolate(plProgress, [0, 1], [height * 0.2, height * 0.86]); // 상단 → 하단
  const plOpacity = interpolate(plProgress, [0.85, 1], [1, 0], clamp); // 끝부분에서만 페이드

  // ── 곡 제목(본 영상 구간별, 경계 페이드) ─────────────────────────
  const t = frame / fps;
  const active = currentTrack(tracks, t, durationSec);
  let titleOpacity = 0;
  if (active) {
    const fadeFrames = Math.round(fps * 0.6);
    const sf = active.start * fps;
    const ef = active.end * fps;
    titleOpacity = Math.min(
      interpolate(frame, [sf, sf + fadeFrames], [0, 1], clamp),
      interpolate(frame, [ef - fadeFrames, ef], [1, 0], clamp),
    );
  }

  // ── 좌하단 블록(부제 위 / 곡 제목 아래, 명확히 분리): 4.9~6.1 타이핑, 6.1~ 본영상 ──
  const typeProgress = interpolate(frame, [TYPE_START * fps, TYPE_END * fps], [0, 1], clamp);
  const inIntroType = frame < TYPE_END * fps;
  const blLeft = width * 0.06;
  const blSubTop = height * 0.73; // #32 부제(위) — 약 4%p(≈50px) 위로
  const blTitleTop = height * 0.815; // #32 곡 제목(아래) — 동일 4%p 위, 간격 8.5%p 유지
  let blSub = "";
  let blTitle = "";
  let blTitleOpacity = 0;
  if (frame >= TYPE_START * fps) {
    if (inIntroType) {
      blSub = subtitleEn.slice(0, Math.floor(typeProgress * subtitleEn.length));
      blTitle = firstTitle.slice(0, Math.floor(typeProgress * firstTitle.length));
      blTitleOpacity = 1;
    } else {
      blSub = subtitleEn;
      blTitle = active ? active.title : "";
      blTitleOpacity = titleOpacity; // 곡 전환 페이드
    }
  }

  const shadow = "0 2px 14px rgba(0,0,0,0.78)";

  return (
    <AbsoluteFill>
      {/* 1) 배경(깨끗한 이미지 — 텍스트 0, Remotion 이 모든 글자를 그린다) */}
      <Img src={staticFile(BG)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      <Audio src={staticFile(AUDIO)} />

      {/* 하단 가독성 스크림(은은) */}
      <div
        style={{
          position: "absolute", left: 0, right: 0, bottom: 0, height: height * 0.42,
          background: "linear-gradient(to top, rgba(0,0,0,0.45), rgba(0,0,0,0))",
        }}
      />

      {/* #37-B WHERE 라벨(상단 중앙, 'Where :' 표기) — #35-A 디자인 설정 적용(미설정 시 현재값). */}
      {locationEn && (
        <div
          style={{
            position: "absolute", top: height * 0.04, width: "100%", textAlign: "center",
            fontFamily: wlFontFamily, fontSize: wlFontSize, fontWeight: wlFontWeight,
            letterSpacing: "0.05em", color: wlColor, opacity: wlOpacity,
            textShadow: "0 2px 12px rgba(0,0,0,0.8)", ...wlStroke,
          }}
        >
          Where : {locationEn}
        </div>
      )}

      {/* 2) 인트로 정지 보조 텍스트(부제 좌중 / 곡제목 우중하단) — 0~4.7 페이드 */}
      {introOpacity > 0.001 && (
        <div style={{ position: "absolute", inset: 0, opacity: introOpacity }}>
          {subtitleEn && (
            <div
              style={{
                position: "absolute", left: width * 0.08, top: height * 0.46,
                fontFamily: SERIF, fontStyle: "italic", color: textColor,
                fontSize: width * 0.026, textShadow: shadow, maxWidth: width * 0.5,
              }}
            >
              {subtitleEn}
            </div>
          )}
          {firstTitle && (
            <div
              style={{
                position: "absolute", right: width * 0.08, bottom: height * 0.2,
                fontFamily: SCRIPT, color: textColor,
                fontSize: width * 0.05, textShadow: shadow, textAlign: "right", maxWidth: width * 0.55,
              }}
            >
              {firstTitle}
            </div>
          )}
        </div>
      )}

      {/* 2b) PLAY LIST — 거대 → 좌하단 이동·축소·페이드(easeInOutCubic). #35-A 디자인 설정 적용. */}
      {plOpacity > 0.001 && (
        <div
          style={{
            position: "absolute",
            left: plX,
            top: plY,
            transform: `translate(-50%, -50%) scale(${plScale})`,
            transformOrigin: "center",
            fontFamily: plFontFamily,
            fontWeight: plFontWeight,
            color: plColor,
            fontSize: LARGE,
            lineHeight: 1,
            letterSpacing: width * 0.012,
            whiteSpace: "nowrap",
            textShadow: shadow,
            opacity: plOpacity * plOpacityMul,
            ...plStroke,
          }}
        >
          PLAY LIST
        </div>
      )}

      {/* 3) 좌하단 블록(타이핑 후 본 영상): 부제(위) + 곡 제목(아래). #36 디자인 설정 적용(미설정 시 현재값). */}
      {blSub && (
        <div
          style={{
            position: "absolute", left: blLeft, top: blSubTop,
            fontFamily: sFontFamily, fontStyle: sFontStyle, fontWeight: sFontWeight,
            color: sColor, opacity: sOpacity,
            fontSize: sFontSize, textShadow: shadow, maxWidth: width * 0.6, ...sStroke,
          }}
        >
          {blSub}
        </div>
      )}
      {blTitle && (
        <div
          style={{
            position: "absolute", left: blLeft, top: blTitleTop, opacity: blTitleOpacity * tOpacityMul,
            fontFamily: tFontFamily, fontStyle: tFontStyle, fontWeight: tFontWeight, color: tColor,
            fontSize: tFontSize, textShadow: shadow, maxWidth: width * 0.7, ...tStroke,
          }}
        >
          {blTitle}
        </div>
      )}

      {/* 4) 맨 아래 굵은 둥근 바 이퀄(3.5초부터 등장, 반투명·감쇠) */}
      <div
        style={{ position: "absolute", inset: 0, opacity: eqIn, transform: `translateY(${eqTranslateY}px)` }}
      >
        {values.map((v, i) => {
          // #31 고역 롤오프 보정 5배 강화(1.6→5.0) — 진짜 음원에서도 우측 막대 활발히 움직임.
          // amp 는 Math.min(1, …) 으로 1에 캡 → 최대 높이(12+maxBarH≈화면 13%)는 그대로(폭주 방지).
          const tilt = 1 + (i / (BARS - 1)) * 5.0;
          const amp = Math.min(1, v * 2.4 * tilt);
          const h = Math.min(maxBarH + 12, Math.max(16, 12 + amp * maxBarH)); // 캡 + 최소 높이
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                bottom: baseBottom,
                left: left + i * slot + (slot - barW) / 2,
                width: barW,
                height: h,
                borderRadius: barW,
                opacity: 0.82,
                background: `linear-gradient(to top, ${c1}, ${c2})`,
              }}
            />
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
