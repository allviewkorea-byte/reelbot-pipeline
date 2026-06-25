// Remotion 렌더 진입점 — music_video.py 가 subprocess 로 호출한다.
//
//   node render.mjs --audio <mp3> --bg <png> --out <mp4> --props '<json>'
//
// props(JSON): { tracks: [{title, start_sec}], mood: string, durationSec: number }
//
// 렌더 경로(자동 선택):
//   1) Lambda(분산, 빠름): REMOTION_SERVE_URL + REMOTION_LAMBDA_FUNCTION_NAME 가 모두 설정되고
//      에셋 공개 URL(--audio-url, --bg-url)이 주어지면 renderMediaOnLambda 로 렌더한다.
//      배포된 번들은 영상마다 다른 audio/bg/character 를 못 담으므로 그 URL 을 inputProps 로 주입한다.
//      분할(--frame-start/--muted)은 로컬 긴영상 전용 전략 → Lambda 는 항상 전체 1샷.
//   2) 로컬(폴백): 위 조건이 안 되거나 Lambda 가 실패하면 기존 방식(bundle + renderMedia)으로.
//
// 자산(오디오·배경)은 로컬 경로일 때 임시 publicDir 로 복사해 staticFile 로 참조한다(원격 URL/file:// CORS 회피).
// Chromium 은 시스템 설치본을 쓴다 — REMOTION_CHROMIUM_EXECUTABLE/PUPPETEER_EXECUTABLE_PATH
// 미설정 시 Remotion 기본(자동 다운로드)로 폴백하나, Railway 에선 Dockerfile 이 env 를 지정한다.

import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import { parseArgs } from "node:util";
import { fileURLToPath } from "node:url";
import { mkdtempSync, copyFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const { values } = parseArgs({
  options: {
    audio: { type: "string" },
    bg: { type: "string" },
    out: { type: "string" },
    props: { type: "string" },
    character: { type: "string" }, // #50 인물 투명 PNG(있을 때만) — staticFile("character.png")
    // Lambda 에셋 공개 URL — 주어지면 Lambda 경로에서 inputProps 로 주입(로컬 경로 대체).
    "audio-url": { type: "string" },
    "bg-url": { type: "string" },
    "character-url": { type: "string" },
    // #43 분할 렌더 — 주어지면 그 프레임 구간만 렌더(frameRange). 미지정 시 전체(기존 동작).
    "frame-start": { type: "string" },
    "frame-end": { type: "string" },
    muted: { type: "boolean" }, // #43 분할 시 비디오만 렌더(오디오는 나중에 풀 mux)
  },
});

for (const k of ["audio", "bg", "out"]) {
  if (!values[k]) {
    console.error(`[remotion] --${k} 인자 필요`);
    process.exit(2);
  }
}

const root = path.dirname(fileURLToPath(import.meta.url));
const props = JSON.parse(values.props || "{}");
const browserExecutable =
  process.env.REMOTION_CHROMIUM_EXECUTABLE ||
  process.env.PUPPETEER_EXECUTABLE_PATH ||
  null;

const COMPOSITION_ID = "MusicViz"; // 실제 composition id(작업지시서의 "MusicVideo" 는 오타).

// #43 분할 구간 — frame-start/end 둘 다 있으면 그 구간만(frameRange). 없으면 전체.
const frameRange =
  values["frame-start"] !== undefined && values["frame-end"] !== undefined
    ? [Number(values["frame-start"]), Number(values["frame-end"])]
    : undefined;

// ── 로컬 렌더(기존 방식, 폴백) ──────────────────────────────────────────────
async function renderLocally() {
  // 자산을 임시 publicDir 로 복사(staticFile 고정 이름).
  const publicDir = mkdtempSync(path.join(tmpdir(), "rmpub-"));
  try {
    copyFileSync(values.audio, path.join(publicDir, "audio.mp3"));
    copyFileSync(values.bg, path.join(publicDir, "bg.png"));
    // 심경하체(번들 TTF) — staticFile("SimgyeongHa.ttf")로 FontFace 로드.
    copyFileSync(path.join(root, "assets", "SimgyeongHa.ttf"), path.join(publicDir, "SimgyeongHa.ttf"));
    // #50 인물 PNG(투명) — 주어졌을 때만 staticFile("character.png")로 스테이징.
    if (values.character) {
      copyFileSync(values.character, path.join(publicDir, "character.png"));
    }
    const serveUrl = await bundle({ entryPoint: path.join(root, "src", "index.ts"), publicDir });
    const composition = await selectComposition({
      serveUrl,
      id: COMPOSITION_ID,
      inputProps: props,
      browserExecutable,
    });
    await renderMedia({
      composition,
      serveUrl,
      codec: "h264",
      outputLocation: values.out,
      inputProps: props,
      browserExecutable,
      chromiumOptions: { gl: "swiftshader" }, // 헤드리스/서버 소프트웨어 렌더링.
      // #38 프레임 품질 상향(1080p 출력 유지) — JPEG 100(거의 무손실), h264 crf 16.
      imageFormat: "jpeg",
      jpegQuality: 100,
      crf: 16,
      ...(frameRange ? { frameRange } : {}), // #43 분할 구간(미지정 시 전체)
      ...(values.muted ? { muted: true } : {}), // #43 분할 시 비디오만
    });
  } finally {
    rmSync(publicDir, { recursive: true, force: true });
  }
}

// ── Lambda 렌더(분산, 빠름) ─────────────────────────────────────────────────
function lambdaEligible() {
  // 분할/muted 는 로컬 긴영상 전략 → Lambda 는 항상 전체 1샷이라 제외.
  if (frameRange || values.muted) return false;
  if (!process.env.REMOTION_SERVE_URL || !process.env.REMOTION_LAMBDA_FUNCTION_NAME) return false;
  // Lambda 는 배포 번들을 공유 → 영상별 audio/bg 공개 URL 필수.
  return Boolean(values["audio-url"] && values["bg-url"]);
}

async function renderWithLambda() {
  const { renderMediaOnLambda, getRenderProgress } = await import("@remotion/lambda/client");
  const region = process.env.AWS_REGION || "us-west-2";
  const functionName = process.env.REMOTION_LAMBDA_FUNCTION_NAME;
  const serveUrl = process.env.REMOTION_SERVE_URL;

  // 에셋 URL 을 inputProps 로 주입(MusicViz 가 staticFile 대신 이 URL 로 로드).
  const inputProps = {
    ...props,
    audioUrl: values["audio-url"],
    bgUrl: values["bg-url"],
    ...(values["character-url"] ? { characterUrl: values["character-url"] } : {}),
  };

  const outName = path.basename(values.out) || "out.mp4";
  const { renderId, bucketName } = await renderMediaOnLambda({
    region,
    functionName,
    serveUrl,
    composition: COMPOSITION_ID,
    inputProps,
    codec: "h264",
    imageFormat: "jpeg",
    jpegQuality: 100,
    crf: 16,
    privacy: "public",
    maxRetries: 3,
    outName,
  });

  // 완료까지 폴링(getRenderProgress). 치명 오류면 throw → 호출부가 로컬 폴백.
  for (;;) {
    const p = await getRenderProgress({ renderId, bucketName, functionName, region });
    if (p.fatalErrorEncountered) {
      throw new Error(p.errors?.[0]?.message || "Lambda 렌더 치명 오류");
    }
    if (p.done) {
      const url = p.outputFile;
      if (!url) throw new Error("Lambda 완료했으나 outputFile 없음");
      // S3 출력 → 로컬 values.out 으로 내려받아 기존 R2 업로드 로직과 동일하게 처리.
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Lambda 출력 다운로드 실패 HTTP ${res.status}`);
      const buf = Buffer.from(await res.arrayBuffer());
      writeFileSync(values.out, buf);
      return;
    }
    await new Promise((r) => setTimeout(r, 3000));
  }
}

// ── 디스패처: Lambda 우선, 실패 시 로컬 폴백 ──────────────────────────────────
const t0 = Date.now();
console.log("[render] Lambda 조건:", JSON.stringify({
  frameRange: frameRange ?? null,
  muted: values.muted ?? false,
  REMOTION_SERVE_URL: !!process.env.REMOTION_SERVE_URL,
  REMOTION_LAMBDA_FUNCTION_NAME: !!process.env.REMOTION_LAMBDA_FUNCTION_NAME,
  audioUrl: values["audio-url"] ? values["audio-url"].slice(0, 60) : null,
  bgUrl: values["bg-url"] ? values["bg-url"].slice(0, 60) : null,
  eligible: lambdaEligible(),
}));
try {
  if (lambdaEligible()) {
    try {
      console.log("[render] Lambda 렌더 시작");
      await renderWithLambda();
      const secs = ((Date.now() - t0) / 1000).toFixed(1);
      console.log(`REMOTION_OK ${values.out} (${secs}s, lambda)`);
    } catch (e) {
      console.warn("[render] Lambda 실패, 로컬 렌더로 폴백:", e?.message || e);
      await renderLocally();
      const secs = ((Date.now() - t0) / 1000).toFixed(1);
      console.log(`REMOTION_OK ${values.out} (${secs}s, local-fallback)`);
    }
  } else {
    await renderLocally();
    const secs = ((Date.now() - t0) / 1000).toFixed(1);
    console.log(`REMOTION_OK ${values.out} (${secs}s, local)`);
  }
} catch (err) {
  console.error("[remotion] 렌더 실패:", err?.stack || err?.message || err);
  process.exit(1);
}
