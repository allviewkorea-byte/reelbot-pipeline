import {
  AbsoluteFill,
  Audio,
  cancelRender,
  continueRender,
  delayRender,
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
import { loadFont as loadBodoni } from "@remotion/google-fonts/BodoniModa";
import { loadFont as loadYoungSerif } from "@remotion/google-fonts/YoungSerif";
import { loadFont as loadLiterata } from "@remotion/google-fonts/Literata";
import { loadFont as loadNotoSerifKR } from "@remotion/google-fonts/NotoSerifKR";
import { loadFont as loadBlackHanSans } from "@remotion/google-fonts/BlackHanSans";
import { loadFont as loadNanumMyeongjo } from "@remotion/google-fonts/NanumMyeongjo";
import { currentTrack, Track } from "./tracks";

// Google Fonts — weight·subset 제한(CJK 폰트의 992개 @font-face 요청 → 브라우저 crash 방지).
const playfair = loadPlayfair("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] });
const dancing = loadDancing("normal", { weights: ["400", "700"], subsets: ["latin"] });
const SERIF = playfair.fontFamily;
const SCRIPT = dancing.fontFamily;

// 심경하체(SimgyeongHa) — Google Fonts 미존재. 레포 번들 TTF 를 render.mjs 가 publicDir 로 복사 →
// staticFile + FontFace 로 로드(R2/신규 의존성 불필요). delayRender 로 렌더가 폰트 로드를 기다린다.
const SIMGYEONGHA = "SimgyeongHa";
if (typeof window !== "undefined" && typeof FontFace !== "undefined") {
  const handle = delayRender("SimgyeongHa 폰트 로드");
  const face = new FontFace(SIMGYEONGHA, `url(${staticFile("SimgyeongHa.ttf")}) format("truetype")`);
  face
    .load()
    .then((loaded) => {
      (document.fonts as unknown as { add(f: FontFace): void }).add(loaded);
      continueRender(handle);
    })
    .catch((err) => cancelRender(err));
}

// #35-A 디자인 본부 프리셋 폰트 — weight·subset 제한(네트워크 요청 최소화).
const PRESET_FONTS: Record<string, string> = {
  Montserrat: loadMontserrat("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }).fontFamily,
  Poppins: loadPoppins("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }).fontFamily,
  "Bebas Neue": loadBebas("normal", { weights: ["400"], subsets: ["latin"] }).fontFamily,
  Oswald: loadOswald("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }).fontFamily,
  Anton: loadAnton("normal", { weights: ["400"], subsets: ["latin"] }).fontFamily,
  Archivo: loadArchivo("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }).fontFamily,
  Inter: loadInter("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }).fontFamily,
  "DM Sans": loadDMSans("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }).fontFamily,
  "Playfair Display": playfair.fontFamily,
  "Cormorant Garamond": loadCormorant("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }).fontFamily,
  "Bodoni Moda": loadBodoni("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }).fontFamily,
  "Young Serif": loadYoungSerif("normal", { weights: ["400"], subsets: ["latin"] }).fontFamily,
  Literata: loadLiterata("normal", { weights: ["400", "500", "600", "700"], subsets: ["latin"] }).fontFamily,
  "Noto Serif KR": loadNotoSerifKR("normal", { weights: ["400", "500", "600", "700"], subsets: ["korean"] }).fontFamily,
  "Black Han Sans": loadBlackHanSans("normal", { weights: ["400"], subsets: ["korean"] }).fontFamily,
  "Nanum Myeongjo": loadNanumMyeongjo("normal", { weights: ["400", "700"], subsets: ["korean"] }).fontFamily,
  SimgyeongHa: SIMGYEONGHA,
};

// 한글 폰트 기본값(제목·부제 미설정 시). 영어 폰트 스택의 두 번째 자리.
const DEFAULT_KR_FONT = "Noto Serif KR";

// 영어 폰트 + 한글 폰트 스택 — 영어 글자는 영어 폰트, 한글 글자는 한글 폰트로 자동 fallback.
function fontStack(en: string, krName?: string): string {
  const kr = PRESET_FONTS[krName ?? ""] ?? PRESET_FONTS[DEFAULT_KR_FONT];
  return `"${en}", "${kr}"`;
}

// #35-A 디자인 설정(채널 설정 본부에서 저장). 비어 있으면 현재 하드코딩값으로 폴백(회귀 0).
type TextStyleCfg = {
  font_family?: string;
  font_size?: number;
  font_weight?: number;
  color?: string;
  opacity?: number;
  italic?: boolean; // #36 title/subtitle 만 사용
  letter_spacing?: number; // 글자 간격(px, 기본 0). 메인 로고에 적용.
  border?: { enabled?: boolean; width?: number; color?: string };
};
export type DesignConfig = {
  play_list?: TextStyleCfg;
  where_label?: TextStyleCfg;
  title?: TextStyleCfg; // #36 곡 제목(좌하단)
  subtitle?: TextStyleCfg; // #36 부제(좌하단)
  playlist_text?: string; // 인라인 편집 — 빈값이면 "PLAY LIST"
  where_text?: string; // 인라인 편집 — 빈값이면 "Where"
  where_label_hidden?: boolean; // Where 라벨 숨김(미지정=true=숨김)
  title_font_kr?: string; // 제목 한글 폰트(미지정=Noto Serif KR)
  subtitle_font_kr?: string; // 부제 한글 폰트(미지정=Noto Serif KR)
  // 요소 위치(0~1 비율, 미지정=기존 기본값 → 회귀 0).
  logo_x?: number;
  logo_y?: number;
  title_x?: number;
  title_y?: number;
  subtitle_x?: number;
  subtitle_y?: number;
  location_x?: number;
  location_y?: number;
  // 요소 크기(배율, 미지정=1.0 → 회귀 0). 0.5~2.0.
  logo_scale?: number;
  title_scale?: number;
  subtitle_scale?: number;
  location_scale?: number;
  logo_underline_weight?: number; // 로고 '_' → 실제 선의 굵기(px, 0.5~20, 기본 2)
  location_letter_spacing?: number; // 라벨 글자 간격(px, 기본 0)
  equalizer?: EqualizerCfg; // 오디오 반응 이퀄(로고 위, pill 막대)
} | null;

// 이퀄라이저(산 모양, 로고 위) 설정 — 미지정 시 기본값.
type EqualizerCfg = {
  color1?: string;
  color2?: string;
  gradient?: "horizontal" | "center";
  max_height?: number;
  width?: number;
  gap_above_logo?: number;
  x?: number; // 가로 위치(0~1, 기본 0.5=중앙)
};

// 로고 텍스트를 '_'(밑줄) 런 단위로 분할 — '_' 문자에만 별도 두께 적용(나머지는 로고 두께).
function logoRuns(text: string): { s: string; underline: boolean }[] {
  const runs: { s: string; underline: boolean }[] = [];
  for (const ch of text) {
    const u = ch === "_";
    const last = runs[runs.length - 1];
    if (last && last.underline === u) last.s += ch;
    else runs.push({ s: ch, underline: u });
  }
  return runs;
}

// 테두리(외곽선) — border.enabled 일 때만 -webkit-text-stroke + paint-order(깔끔한 외곽).
function strokeStyle(b?: { enabled?: boolean; width?: number; color?: string }): React.CSSProperties {
  if (!b?.enabled) return {};
  return { WebkitTextStroke: `${b.width ?? 1}px ${b.color ?? "#000000"}`, paintOrder: "stroke fill" };
}

// 두 hex 색을 t(0~1)로 선형 보간(이퀄 그라데이션 막대별 색).
function mixHex(a: string, b: string, t: number): string {
  const p = (h: string) => {
    const m = /^#?([0-9a-f]{6})$/i.exec(h.trim());
    const n = m ? parseInt(m[1], 16) : 0;
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  };
  const [r1, g1, b1] = p(a);
  const [r2, g2, b2] = p(b);
  const k = Math.max(0, Math.min(1, t));
  const ch = (x: number, y: number) => Math.round(x + (y - x) * k);
  return `rgb(${ch(r1, r2)}, ${ch(g1, g2)}, ${ch(b1, b2)})`;
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
  showPlaylist?: boolean; // #39 영상별 PLAY LIST 표시(기본 true; false 면 인트로·도킹 모두 안 그림)
  hasCharacter?: boolean; // #50 인물 레이어(투명 PNG)를 최상단에 얹을지(기본 false → 기존 2레이어)
  // Lambda 렌더용 에셋 공개 URL(없으면 staticFile 로 폴백 = 로컬 렌더 100% 동일).
  // Lambda 는 배포된 번들을 공유하므로 영상마다 다른 audio/bg/character 를 publicDir 로
  // 못 넣는다 → URL 을 props 로 주입한다. 디자인·레이아웃·모션은 일절 무관.
  audioUrl?: string;
  bgUrl?: string;
  characterUrl?: string;
};

const AUDIO = "audio.mp3";
const BG = "bg.png";
const CHARACTER = "character.png"; // #50 인물 투명 PNG(hasCharacter 일 때만 staticFile 로 존재)

const EQ_BARS = 20; // 새 이퀄(산 모양) 막대 수
const NUM_SAMPLES = 256; // visualizeAudio 는 2의 거듭제곱 필요.
const SMOOTH_FRAMES = 2; // #34 활발한 반응 — 평균 윈도우 4→2(빠른 감쇠). 진폭·tilt·캡 불변.

// 모션 타임라인(초·프레임). 기준 FPS=30 이나 실제 fps 는 useVideoConfig 에서 읽는다.
// A: where;____·이퀄은 프레임 0부터 고정(페이드 없음). B: 라벨 3초 후 페이드인.
// C: 제목 4초부터 좌→우 타이핑. D: 부제는 제목 완료 + PAUSE 후. E: 곡 전환 시 재타이핑.
const LABEL_FADE_START_SEC = 3; // 라벨 페이드 시작(3초)
const LABEL_FADE_DUR_SEC = 1; // 라벨 페이드 길이(1초 → 4초에 완전 등장)
const TITLE_START_SEC = 4; // 첫 곡 제목 타이핑 시작(4초, 라벨 페이드 완료 후)
const CHAR_INTERVAL = 5; // 글자당 5프레임(손글씨 느낌, 느리게)
const TITLE_SUBTITLE_PAUSE = 15; // 제목 마지막 글자 → 부제 시작 사이 pause(프레임)
const CHAR_FADE_FRAMES = 2; // 글자 등장 시 opacity 0→1 페이드(프레임)

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

export const MusicViz: React.FC<MusicVizProps> = ({ tracks, mood, durationSec, vizSpec, designConfig, showPlaylist, hasCharacter, audioUrl, bgUrl, characterUrl }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  // 에셋 소스: URL props 우선(Lambda), 없으면 staticFile(로컬 렌더 — 회귀 0).
  const audioSrc = audioUrl || staticFile(AUDIO);
  const bgSrc = bgUrl || staticFile(BG);
  const characterSrc = characterUrl || staticFile(CHARACTER);
  const audioData = useAudioData(audioSrc);

  // #27: 모든 텍스트 순백 고정(vizSpec.text_color 무시). 이퀄 색은 design_config 가 결정.
  const textColor = "#FFFFFF";
  const subtitleEn = (vizSpec?.subtitle_en || "").trim();
  const locationEn = (vizSpec?.location_en || "").trim() || "City View"; // #33: 항상 WHERE 표시(폴백)

  // ── #35-A 디자인 설정: 미지정 필드는 현재 하드코딩값으로 폴백(designConfig 비면 100% 동일) ──
  const plCfg = designConfig?.play_list ?? {};
  const wlCfg = designConfig?.where_label ?? {};
  // 인라인 편집 텍스트(빈값=기본값 폴백). 영상 반영.
  const playlistText = (designConfig?.playlist_text || "").trim() || "PLAY LIST";
  // 라벨 텍스트 = 입력값(where_text) 그대로. 비었으면 자동 지역명(vizSpec) 폴백. 접두사 없음.
  const labelText = (designConfig?.where_text || "").trim() || locationEn;
  const locLetterSpacing = designConfig?.location_letter_spacing ?? 0;
  const whereLabelHidden = designConfig?.where_label_hidden ?? true; // 기본 숨김
  const plFontFamily = PRESET_FONTS[plCfg.font_family ?? ""] ?? SERIF;
  const plFontWeight = plCfg.font_weight ?? 700;
  const plUnderlineThickness = designConfig?.logo_underline_weight ?? 2; // '_' → 실제 선 굵기(px, 기본 2)
  const plColor = plCfg.color ?? textColor;
  const plOpacityMul = plCfg.opacity ?? 1;
  const plFontSize = plCfg.font_size ?? height * 0.3;
  const plStroke = strokeStyle(plCfg.border);
  const wlFontFamily = PRESET_FONTS[wlCfg.font_family ?? ""] ?? "sans-serif";
  const wlFontSize = (wlCfg.font_size ?? width * 0.012) * (designConfig?.location_scale ?? 1);
  const wlFontWeight = wlCfg.font_weight ?? 600;
  const wlColor = wlCfg.color ?? "#FFFFFF";
  const wlOpacity = wlCfg.opacity ?? 0.9;
  const wlStroke = strokeStyle(wlCfg.border);

  // ── #36 제목·부제(좌하단 블록): title/subtitle 키 없으면 현재값으로 폴백(기울임 포함 회귀 0) ──
  const tCfg = designConfig?.title;
  const sCfg = designConfig?.subtitle;
  const tFontEn = tCfg ? (PRESET_FONTS[tCfg.font_family ?? ""] ?? SCRIPT) : SCRIPT;
  const tFontFamily = fontStack(tFontEn, designConfig?.title_font_kr); // 영어+한글 스택
  const tFontWeight = tCfg?.font_weight; // 미지정이면 undefined → 현재(미설정=400)
  const tColor = tCfg?.color ?? textColor;
  const tFontSize = (tCfg?.font_size ?? width * 0.044) * (designConfig?.title_scale ?? 1);
  const tFontStyle = tCfg ? (tCfg.italic ? "italic" : "normal") : undefined; // 현재 미설정
  const tOpacityMul = tCfg?.opacity ?? 1;
  const tStroke = strokeStyle(tCfg?.border);
  const sFontEn = sCfg ? (PRESET_FONTS[sCfg.font_family ?? ""] ?? SERIF) : SERIF;
  const sFontFamily = fontStack(sFontEn, designConfig?.subtitle_font_kr); // 영어+한글 스택
  const sFontWeight = sCfg?.font_weight;
  const sColor = sCfg?.color ?? textColor;
  const sFontSize = (sCfg?.font_size ?? width * 0.02) * (designConfig?.subtitle_scale ?? 1);
  const sFontStyle = sCfg ? (sCfg.italic ? "italic" : "normal") : "italic"; // 현재 항상 italic
  const sOpacity = sCfg?.opacity ?? 1;
  const sStroke = strokeStyle(sCfg?.border);

  // ── 이퀄 막대 진폭(최근 프레임 평균으로 감쇠) — EQ_BARS 개 ──────────
  // 오디오 디코드가 안 되는 경우에도 막대가 보이도록 idle 사인으로 폴백(가시성 보장).
  const values: number[] = new Array(EQ_BARS).fill(0);
  if (audioData) {
    const windows = [];
    for (let d = 0; d < SMOOTH_FRAMES; d++) {
      windows.push(
        visualizeAudio({ audioData, frame: Math.max(0, frame - d), fps, numberOfSamples: NUM_SAMPLES }),
      );
    }
    for (let i = 0; i < EQ_BARS; i++) {
      const idx = 1 + Math.round((i / (EQ_BARS - 1)) * (NUM_SAMPLES * 0.45));
      let sum = 0;
      for (const w of windows) sum += w[idx] || 0;
      values[i] = sum / windows.length;
    }
  } else {
    for (let i = 0; i < EQ_BARS; i++) {
      values[i] = 0.22 + 0.16 * (0.5 + 0.5 * Math.sin(frame / 6 + i * 0.5));
    }
  }

  // ── B. 라벨 페이드: 0~3초 0 → 3~4초 0→1 → 이후 1 고정. 절대 프레임 기준(곡 전환에도 유지). ──
  const labelFade = interpolate(
    frame,
    [LABEL_FADE_START_SEC * fps, (LABEL_FADE_START_SEC + LABEL_FADE_DUR_SEC) * fps],
    [0, 1],
    clamp,
  );

  // ── 요소 위치(0~1 비율 → px). 미지정 시 기존 기본값(회귀 0). #E 위치 슬라이더 ──
  const logoX = width * (designConfig?.logo_x ?? 0.5); // 기본 가로 중앙
  const logoY = height * (designConfig?.logo_y ?? 0.5); // 기본 세로 중앙
  const titleLeft = width * (designConfig?.title_x ?? 0.06);
  const titleTop = height * (designConfig?.title_y ?? 0.67);
  const subLeft = width * (designConfig?.subtitle_x ?? 0.06);
  const subTop = height * (designConfig?.subtitle_y ?? 0.755);
  const locX = width * (designConfig?.location_x ?? 0.5);
  const locY = height * (designConfig?.location_y ?? 0.04);

  // ── A. PLAY LIST(메인 로고): 프레임 0부터 끝까지 고정. 페이드·이동·축소 없음(opacity 1). ──
  const LARGE = plFontSize; // 폰트 높이 ~30%(기본) — #35-A 설정 시 그 px.
  const plScale = designConfig?.logo_scale ?? 1; // #크기 슬라이더(0.5~2.0, 기본 1)

  // ── C·D·E. 제목·부제 타이핑(좌→우, 글자당 CHAR_INTERVAL). 곡 전환 시 그 곡 시작에서 재타이핑. ──
  const t = frame / fps;
  const active = currentTrack(tracks, t, durationSec);
  const curTitle = active ? (active.title || "").trim() : "";
  const curTitleLen = curTitle.length;
  // 타이핑 시작: 첫 곡은 4초(라벨 등장 후), 이후 곡은 그 곡 시작 프레임.
  const isFirstSong = !active || active.start <= 1e-3;
  const typeStartF = isFirstSong ? TITLE_START_SEC * fps : active!.start * fps;
  // 제목 마지막 글자 등장 프레임 → +PAUSE 후 부제 시작(제목 글자수에 따라 동적).
  const titleLastCharF = typeStartF + Math.max(0, curTitleLen - 1) * CHAR_INTERVAL;
  const subStartF = (curTitleLen > 0 ? titleLastCharF : typeStartF) + TITLE_SUBTITLE_PAUSE;

  // 한 글자씩 좌→우로 나타나는 span 배열(글자별 2프레임 fade). startF = 첫 글자 등장 프레임.
  const typedSpans = (text: string, startF: number) =>
    Array.from(text).map((ch, i) => {
      const cf = startF + i * CHAR_INTERVAL;
      const op = interpolate(frame, [cf, cf + CHAR_FADE_FRAMES], [0, 1], clamp);
      return (
        <span key={i} style={{ opacity: op, whiteSpace: "pre" }}>
          {ch}
        </span>
      );
    });

  // ── 이퀄(산 모양) 설정 + 위치(로고 바로 위, 중앙 정렬) ──────────────
  const eq = designConfig?.equalizer ?? {};
  const eqColor1 = eq.color1 ?? "#FF00AA";
  const eqColor2 = eq.color2 ?? "#00AAFF";
  const eqGradient = eq.gradient ?? "center";
  const eqMaxH = eq.max_height ?? 65;
  const eqWidth = eq.width ?? 260;
  const eqGap = eq.gap_above_logo ?? 120;
  const eqX = width * (eq.x ?? 0.5); // 이퀄 가로 위치(0.5=중앙)
  const logoTop = logoY - (LARGE * plScale) / 2; // 로고 윗변(크기 배율 반영 → 이퀄 겹침 방지)
  const eqBottom = logoTop - eqGap; // 이퀄 막대 바닥(= 로고 위 eqGap)
  const eqBarSlot = eqWidth / EQ_BARS;
  const eqBarW = eqBarSlot * 0.55;

  const shadow = "0 2px 14px rgba(0,0,0,0.78)";

  return (
    <AbsoluteFill>
      {/* 1) 배경(깨끗한 이미지 — 텍스트 0, Remotion 이 모든 글자를 그린다) */}
      <Img src={bgSrc} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      <Audio src={audioSrc} />

      {/* 하단 가독성 스크림(은은) */}
      <div
        style={{
          position: "absolute", left: 0, right: 0, bottom: 0, height: height * 0.42,
          background: "linear-gradient(to top, rgba(0,0,0,0.45), rgba(0,0,0,0))",
        }}
      />

      {/* 라벨 — 'Where :' 접두사 없이 입력값(where_text) 그대로 표시. 위치는 location_x/location_y.
          글자 간격은 location_letter_spacing. where_label_hidden(기본 true)이면 렌더 안 함. */}
      {labelText && !whereLabelHidden && (
        <div
          style={{
            position: "absolute", left: locX, top: locY, transform: "translateX(-50%)", textAlign: "center",
            fontFamily: wlFontFamily, fontSize: wlFontSize, fontWeight: wlFontWeight,
            letterSpacing: locLetterSpacing, color: wlColor, opacity: wlOpacity * labelFade,
            textShadow: wlCfg.border?.enabled ? "0 2px 12px rgba(0,0,0,0.8)" : "none", whiteSpace: "nowrap", ...wlStroke,
          }}
        >
          {labelText}
        </div>
      )}

      {/* 2) PLAY LIST(메인 로고) — A: 프레임 0부터 고정. logo_x/logo_y 위치. #39 영상별 표시. */}
      {showPlaylist !== false && (
        <div
          style={{
            position: "absolute",
            left: logoX,
            top: logoY,
            transform: `translate(-50%, -50%) scale(${plScale})`,
            transformOrigin: "center",
            fontFamily: plFontFamily,
            fontWeight: plFontWeight,
            color: plColor,
            fontSize: LARGE,
            lineHeight: 1,
            letterSpacing: plCfg.letter_spacing ?? 0, // #5 글자 간격(기본 0 → 미리보기와 일치)
            whiteSpace: "nowrap",
            textShadow: plCfg.border?.enabled ? shadow : "none",
            opacity: plOpacityMul,
            ...plStroke,
          }}
        >
          {logoRuns(playlistText).map((r, i) => r.underline ? (
            // '_' 런 → 토막 없는 단일 가로 선(언더스코어 문자 제거). 너비 ≈ 글자수 × 0.6em.
            <span key={i} style={{ display: "inline-block", width: `${r.s.length * 0.6}em`, height: plUnderlineThickness, borderRadius: 9999, background: plColor, verticalAlign: "-0.1em" }} />
          ) : (
            <span key={i}>{r.s}</span>
          ))}
        </div>
      )}

      {/* 3) 제목·부제 — C·D·E: 좌→우 글자별 타이핑(곡마다 재타이핑). 위치는 title_x/y, subtitle_x/y. */}
      {subtitleEn && (
        <div
          style={{
            position: "absolute", left: subLeft, top: subTop,
            fontFamily: sFontFamily, fontStyle: sFontStyle, fontWeight: sFontWeight,
            color: sColor, opacity: sOpacity,
            fontSize: sFontSize, textShadow: sCfg?.border?.enabled ? shadow : "none", maxWidth: width * 0.6, ...sStroke,
          }}
        >
          {typedSpans(subtitleEn, subStartF)}
        </div>
      )}
      {curTitle && (
        <div
          style={{
            position: "absolute", left: titleLeft, top: titleTop, opacity: tOpacityMul,
            fontFamily: tFontFamily, fontStyle: tFontStyle, fontWeight: tFontWeight, color: tColor,
            fontSize: tFontSize, textShadow: tCfg?.border?.enabled ? shadow : "none", maxWidth: width * 0.7, ...tStroke,
          }}
        >
          {typedSpans(curTitle, typeStartF)}
        </div>
      )}

      {/* 4) 이퀄 — A: 프레임 0부터 고정(페이드 없음). 로고 바로 위, 가로 위치 eq.x. 오디오 반응 pill 막대. */}
      <div
        style={{
          position: "absolute",
          left: eqX,
          top: eqBottom - eqMaxH,
          width: eqWidth,
          height: eqMaxH,
          transform: "translateX(-50%)",
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "center",
          gap: eqBarSlot - eqBarW,
        }}
      >
        {values.map((v, i) => {
          // 오디오 진폭만으로 높이 결정(산 모양 envelope 제거 → 음악에 자유롭게 반응).
          const tilt = 1 + (i / (EQ_BARS - 1)) * 5.0; // 고역 롤오프 보정(기존 결 유지)
          // #8 파동 세기 강화: 진폭 배율 2.4→5.5(약 2.3배). 소리 없어도 최소 10% 유지(막대 안 사라짐).
          const amp = Math.min(1, v * 5.5 * tilt);
          const h = Math.max(eqMaxH * 0.1, amp * eqMaxH);
          // 그라데이션: horizontal=좌→우 / center=가운데→바깥.
          const tCol = eqGradient === "center"
            ? Math.abs((i / (EQ_BARS - 1)) - 0.5) * 2
            : i / (EQ_BARS - 1);
          return (
            <div
              key={i}
              style={{
                width: eqBarW,
                height: h,
                borderRadius: "9999px 9999px 0 0", // 위만 둥글게, 아래 직각(선에서 솟는 느낌)
                background: mixHex(eqColor1, eqColor2, tCol),
              }}
            />
          );
        })}
      </div>

      {/* 5) #50 인물(투명 PNG) — 최상단 레이어(DOM 마지막 = z 최상). hasCharacter 일 때만 그린다.
          objectFit:contain 으로 원본 비율 유지(잘림 없음). 투명부로 배경·PLAYLIST·이퀄이 비쳐
          인물이 앞에 선 효과. 미지정이면 JSX 자체가 없어 기존 렌더와 100% 동일(회귀 0). */}
      {hasCharacter && (
        <Img
          src={characterSrc}
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            objectFit: "contain",
          }}
        />
      )}
    </AbsoluteFill>
  );
};
