// Remotion 렌더 진입점 — music_video.py 가 subprocess 로 호출한다.
//
//   node render.mjs --audio <mp3> --bg <png> --out <mp4> --props '<json>'
//
// props(JSON): { tracks: [{title, start_sec}], mood: string, durationSec: number }
//
// 자산(오디오·배경)은 임시 publicDir 로 복사해 staticFile 로 참조한다(원격 URL/file:// CORS 회피).
// Chromium 은 시스템 설치본을 쓴다 — REMOTION_CHROMIUM_EXECUTABLE/PUPPETEER_EXECUTABLE_PATH
// 미설정 시 Remotion 기본(자동 다운로드)로 폴백하나, Railway 에선 Dockerfile 이 env 를 지정한다.

import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import { parseArgs } from "node:util";
import { fileURLToPath } from "node:url";
import { mkdtempSync, copyFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const { values } = parseArgs({
  options: {
    audio: { type: "string" },
    bg: { type: "string" },
    out: { type: "string" },
    props: { type: "string" },
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

// 자산을 임시 publicDir 로 복사(staticFile 고정 이름).
const publicDir = mkdtempSync(path.join(tmpdir(), "rmpub-"));
copyFileSync(values.audio, path.join(publicDir, "audio.mp3"));
copyFileSync(values.bg, path.join(publicDir, "bg.png"));

const t0 = Date.now();
try {
  const serveUrl = await bundle({
    entryPoint: path.join(root, "src", "index.ts"),
    publicDir,
  });
  const composition = await selectComposition({
    serveUrl,
    id: "MusicViz",
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
    // #38 프레임 품질 상향(1080p 출력 유지) — 중간 프레임 JPEG 80→100(거의 무손실),
    // h264 crf 18→16(압축 손실↓). png 대신 jpeg100 으로 절충(렌더 시간 부담 최소).
    imageFormat: "jpeg",
    jpegQuality: 100,
    crf: 16,
  });
  const secs = ((Date.now() - t0) / 1000).toFixed(1);
  console.log(`REMOTION_OK ${values.out} (${secs}s)`);
} catch (err) {
  console.error("[remotion] 렌더 실패:", err?.stack || err?.message || err);
  process.exit(1);
} finally {
  rmSync(publicDir, { recursive: true, force: true });
}
