"""사연 트랙 — ffmpeg 합성 엔진 (PR-S4).

S1(자막·모션) + S2(씬 이미지) + S3(오디오·scene_timings) → 완성 mp4
(9:16, 1080x1920, 30fps). 작업 지시서 부록 §4 의 검증된 레시피를 그대로 이식한다.

단계 (Railway 메모리 고려해 분리):
  1) 이미지·오디오 로컬 다운로드(temp)
  2) 씬별 켄번즈 클립 (scale 2160:3840 → zoompan → 1080x1920), 모션별 z/x/y 식
  3) 크로스페이드 체인(0.6s) — 전환 중심이 씬 경계(쉼 중앙, S3가 보정)에 오도록
     클립 길이를 보정해 총 길이 = 오디오 total 유지
  4) ASS 자막(씬별 [start,end), highlight 노란 강조) 번인 + 음성 mux
  5) R2 업로드 → video_url

⚠️ zoompan/xfade 는 재인코딩 필요(기존 concat -c copy 와 다름). ffmpeg/ffprobe 필수.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

import httpx

from adapters import r2_storage

logger = logging.getLogger(__name__)

W, H = 1080, 1920
FPS = 30
XFADE = 0.6          # 크로스페이드 길이(초) — §4
PAN_ZOOM = 1.12      # pan 모션의 고정 줌 배율
# Ken Burns 작업 캔버스. 최대 줌 1.25 만큼만 업스케일(1080·1.25=1350, 1920·1.25=2400)
# 해서 줌 여유를 주되 4K(2160x3840) 대비 픽셀수를 ~2.6배 줄여 Railway 메모리 초과를 막는다.
WORK_W, WORK_H = 1350, 2400
# Railway 컨테이너 메모리/CPU 완화: 빠른 프리셋 + 스레드 제한(프레임 스레드 버퍼 절감).
# 화질은 Shorts 수준(crf 20) 유지.
PRESET = "veryfast"
THREADS = "2"
_FONT = "Noto Sans CJK KR"


def _require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"{tool} 가 PATH 에 없습니다 — 합성에 ffmpeg 필요.")


def _run(args: list[str], cwd: Path) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", *args], cwd=str(cwd), capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg 오류:\n{result.stderr[-2000:]}")


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nokey=1:noprint_wrappers=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def _fetch(url_or_path: str, dest: Path) -> None:
    """http(s) URL 이면 다운로드, 로컬 경로면 복사."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if url_or_path.startswith(("http://", "https://")):
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            resp = client.get(url_or_path)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
    else:
        shutil.copy(url_or_path, dest)


def _zoompan_expr(motion: str, frames: int) -> tuple[str, str, str]:
    """모션별 (z, x, y) zoompan 식. iw/ih 는 작업 캔버스(WORK_WxWORK_H) 기준이며
    식이 상대값이라 캔버스 크기가 바뀌어도 그대로 동작한다."""
    f = max(frames, 2)
    cx = "iw/2-(iw/zoom/2)"
    cy = "ih/2-(ih/zoom/2)"
    if motion == "zoom_out":
        return f"1.25-0.25*on/{f - 1}", cx, cy
    if motion == "pan_right":
        return f"{PAN_ZOOM}", f"(iw-iw/zoom)*on/{f - 1}", cy
    if motion == "pan_left":
        return f"{PAN_ZOOM}", f"(iw-iw/zoom)*(1-on/{f - 1})", cy
    # 기본: zoom_in
    return f"1+0.25*on/{f - 1}", cx, cy


def _ken_burns_clip(image: Path, motion: str, frames: int, out: Path, cwd: Path) -> None:
    z, x, y = _zoompan_expr(motion, frames)
    # 입력이 9:16 이 아니어도(예: 752x1392) 작업 캔버스를 '덮도록' 키운 뒤 중앙 crop →
    # 늘어짐 없이 WORK_WxWORK_H 로 정규화. zoompan 출력은 1080x1920, setsar=1 로 SAR 통일.
    # 모든 클립이 1080x1920·SAR 1:1 로 균일해져 xfade/concat 에서 크기·SAR 불일치가 없다.
    vf = (
        f"scale={WORK_W}:{WORK_H}:force_original_aspect_ratio=increase,"
        f"crop={WORK_W}:{WORK_H},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={FPS},"
        f"setsar=1,format=yuv420p"
    )
    _run([
        "-i", image.name,
        "-vf", vf,
        "-c:v", "libx264", "-preset", PRESET, "-crf", "20", "-threads", THREADS,
        "-r", str(FPS), "-frames:v", str(frames),
        out.name,
    ], cwd=cwd)


def _xfade_chain(clips: list[Path], clip_durs: list[float], out: Path, cwd: Path) -> None:
    """클립들을 0.6s 크로스페이드로 이어붙인다(재인코딩). 클립 1개면 그대로 복사."""
    n = len(clips)
    if n == 1:
        shutil.copy(cwd / clips[0].name, cwd / out.name)
        return

    inputs: list[str] = []
    for c in clips:
        inputs += ["-i", c.name]

    # offset: cum 은 직전까지 누적 길이. 매 xfade 는 0.6s 겹친다.
    filt: list[str] = []
    cum = clip_durs[0]
    prev = "0"
    for k in range(1, n):
        offset = round(cum - XFADE, 3)
        label = "vout" if k == n - 1 else f"v{k}"
        filt.append(
            f"[{prev}][{k}]xfade=transition=fade:duration={XFADE}:offset={offset}[{label}]"
        )
        cum = cum + clip_durs[k] - XFADE
        prev = label

    _run([
        *inputs,
        "-filter_complex", ";".join(filt),
        "-map", "[vout]",
        "-c:v", "libx264", "-preset", PRESET, "-crf", "20", "-threads", THREADS,
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        out.name,
    ], cwd=cwd)


def _ass_time(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t - h * 3600 - m * 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _ass_text(subtitle: str, highlight: str) -> str:
    """자막 텍스트. highlight 구를 노란색으로 감싼다(§4)."""
    text = subtitle.strip()
    if highlight and highlight in text:
        text = text.replace(
            highlight, f"{{\\c&H00F0FF&}}{highlight}{{\\c&HFFFFFF&}}", 1
        )
    return text.replace("\r\n", "\\N").replace("\n", "\\N")


def _build_ass(items: list[dict], ass_path: Path) -> None:
    """items: [{start, end, subtitle, highlight}]. §4 스타일(Noto Sans CJK KR, 강조색)."""
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "WrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{_FONT},74,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "1,0,0,0,100,100,0,0,1,5,3,2,40,40,340,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    lines = [header]
    for it in items:
        text = _ass_text(it.get("subtitle", ""), it.get("highlight", ""))
        if not text:
            continue
        lines.append(
            f"Dialogue: 0,{_ass_time(it['start'])},{_ass_time(it['end'])},"
            f"Default,,0,0,0,,{text}\n"
        )
    ass_path.write_text("".join(lines), encoding="utf-8")


def _burn_and_mux(video: Path, audio: Path, ass: Path, out: Path, cwd: Path) -> None:
    _run([
        "-i", video.name,
        "-i", audio.name,
        "-vf", f"ass={ass.name}",
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", PRESET, "-crf", "20", "-threads", THREADS,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        out.name,
    ], cwd=cwd)


def generate_assemble(
    job_id: str,
    scenes: list[dict],
    scene_timings: list[dict],
    audio_url: str,
    output_dir: str | None = None,
    progress_cb=None,
) -> dict:
    """씬 이미지 + 타이밍 + 자막 + 음성 → 완성 mp4. Returns {"video_url", ...}."""
    _require_ffmpeg()
    if not scenes:
        raise ValueError("scenes 가 비어 있습니다.")
    if not audio_url:
        raise ValueError("audio_url 이 필요합니다.")

    timing_by_idx = {t["index"]: t for t in scene_timings}
    out_dir = Path(output_dir or f"output/sayeon/final/{job_id}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) 오디오 다운로드
    if progress_cb:
        progress_cb(5, "오디오/이미지 받는 중...")
    audio_local = out_dir / "narration.wav"
    _fetch(audio_url, audio_local)

    # 2) 씬별 켄번즈 클립 + 클립 길이 보정(전환 중심=씬 경계)
    n = len(scenes)
    clips: list[Path] = []
    clip_durs: list[float] = []
    ass_items: list[dict] = []
    for i, scene in enumerate(scenes):
        idx = scene.get("index", i + 1)
        timing = timing_by_idx.get(idx)
        if timing is None:
            raise ValueError(f"씬 {idx} 의 scene_timings 누락")
        disp = float(timing["duration"])
        # 양 끝 클립은 +0.3, 중간 클립은 +0.6 보정 → xfade 후 총 길이 = total 유지(§4)
        pad = 0.3 if (i == 0 or i == n - 1) and n > 1 else (0.0 if n == 1 else XFADE)
        frames = max(2, round((disp + pad) * FPS))
        clip_durs.append(frames / FPS)

        if progress_cb:
            progress_cb(10 + int(i / n * 50), f"씬 {idx} 켄번즈 클립...")
        img_local = out_dir / f"scene_{idx}.png"
        _fetch(scene["image_url"], img_local)
        clip = out_dir / f"clip_{idx}.mp4"
        _ken_burns_clip(img_local, scene.get("motion", "zoom_in"), frames, clip, out_dir)
        clips.append(clip)

        ass_items.append({
            "start": float(timing["start"]),
            "end": float(timing["end"]),
            "subtitle": scene.get("subtitle", ""),
            "highlight": scene.get("highlight", ""),
        })

    # 3) 크로스페이드 체인
    if progress_cb:
        progress_cb(65, "크로스페이드 합치는 중...")
    combined = out_dir / "v_combined.mp4"
    _xfade_chain(clips, clip_durs, combined, out_dir)

    # 4) 자막 번인 + 음성 mux
    if progress_cb:
        progress_cb(80, "자막·음성 합성 중...")
    ass_path = out_dir / "subs.ass"
    _build_ass(ass_items, ass_path)
    final = out_dir / "final.mp4"
    _burn_and_mux(combined, audio_local, ass_path, final, out_dir)
    total_duration = round(_duration(final), 3)

    # 5) R2 업로드
    if progress_cb:
        progress_cb(95, "영상 R2 업로드 중...")
    video_url = str(final)
    persistent = False
    if r2_storage.is_available():
        try:
            video_url = r2_storage.upload_sayeon_video(str(final), job_id)
            persistent = True
        except Exception as e:  # noqa: BLE001
            logger.warning("최종 영상 R2 업로드 실패, 로컬 경로 사용: %s", e)
    else:
        logger.warning("R2 미설정 — 최종 영상이 로컬에만 있습니다.")

    if progress_cb:
        progress_cb(100, "완료")
    return {
        "video_url": video_url,
        "persistent": persistent,
        "total_duration": total_duration,
        "scene_count": n,
    }
