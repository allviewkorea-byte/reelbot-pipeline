"""음악 영상화 1차 (Rooftop Music) — 믹스 mp3 → 유튜브용 mp4.

비주얼 = 주제 분위기 배경(gpt-image-1, 가로) + Ken Burns 미세 모션 + 오디오
비주얼라이저(ffmpeg showwaves) + 텍스트(주제 제목 + 곡 전환 시 현재 곡 제목).
16:9 1920x1080 H.264, 믹스 길이만큼, 믹스 오디오 그대로.

⚠️ 가사 자막은 2차(#6b) — 이번엔 제외.

배경 이미지는 gpt-image-1(기존 패턴 재사용, 가로 1536x1024)로 1장 만들어
R2 music-videos/{slug}/bg.png 에 보존(멱등). 완성 mp4 는 music-videos/{slug}/{id}.mp4.
ffmpeg 헬퍼는 백곰 엔진과 결합하지 않도록 이 모듈에 소량 복제(subprocess).
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

from adapters import r2_storage

logger = logging.getLogger(__name__)

W, H = 1920, 1080
FPS = 30
# 채널 톤 컬러(디자인 액센트: 보라·시안) — 비주얼라이저 색.
_VIZ_COLORS = "0x8b5cf6|0x22d3ee"
_IMAGE_MODEL = "gpt-image-1"
_IMAGE_SIZE = "1536x1024"  # 가로
_IMAGE_QUALITY = "high"
_BG_NAME = "bg.png"


# ── ffmpeg 헬퍼(디커플링 복제) ───────────────────────────────────────────
def _require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"{tool} 가 PATH 에 없습니다 — 영상 합성에 ffmpeg 필요.")


def _run(args: list[str], cwd: Path | None = None) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", *args],
        cwd=(str(cwd) if cwd else None),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg 오류:\n{result.stderr[-2500:]}")


def _duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nokey=1:noprint_wrappers=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def _fetch(url_or_path: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if url_or_path.startswith(("http://", "https://")):
        with httpx.Client(timeout=300.0, follow_redirects=True) as c:
            r = c.get(url_or_path)
            r.raise_for_status()
            dest.write_bytes(r.content)
    else:
        shutil.copy(url_or_path, dest)


def _stage_font(work: Path) -> str:
    """drawtext 폰트(한국어)를 work 로 복사하고 **상대경로** fontfile 인자를 반환.

    절대경로(특히 Windows 'C:\\...\\malgun.ttf')를 filtergraph 에 직접 쓰면 ':'·'\\' 가
    파싱을 깨뜨린다. 폰트를 work/font.ttf 로 복사하고 cwd=work + 상대명으로 회피한다
    (백곰 sayeon 의 cwd+상대명 선례와 동일). 폰트 파일이 없으면 fontconfig 이름 폴백.
    """
    p = os.getenv("SUBTITLE_FONT_PATH", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf")
    if os.path.exists(p):
        shutil.copy(p, work / "font.ttf")
        return "fontfile=font.ttf"
    return "font=NanumGothic"


# ── 배경 이미지 (gpt-image-1, 가로) ──────────────────────────────────────
def image_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _bg_prompt(theme: dict) -> str:
    genre = theme.get("genre", "")
    mood = theme.get("mood", "")
    situation = theme.get("situation", "")
    style = theme.get("style_prompt", "")
    return (
        f"Atmospheric cinematic background scene for {genre} music. "
        f"Mood: {mood}. Setting: {situation}. {style}. "
        "Wide horizontal 16:9 composition, soft depth of field, rich ambient lighting, "
        "no text, no words, no letters, no people in focus. Immersive, aesthetic, high quality."
    )


def generate_background(theme: dict, out_path: str, *, force: bool = False) -> str:
    """주제 분위기 배경 1장(gpt-image-1, 가로) → out_path. R2 멱등(있으면 다운로드).

    R2 music-videos/{slug}/bg.png 에 보존. force=True 면 무조건 재생성.
    """
    slug = theme.get("slug") or theme.get("theme_slug") or "untitled"
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # 멱등: 이미 R2 에 있으면 재사용(비용 0).
    if not force and r2_storage.music_video_exists(slug, _BG_NAME):
        logger.info("[video] 배경 이미 존재 — 재사용 slug=%s", slug)
        r2_storage.download_music_object(
            r2_storage.music_video_key(slug, _BG_NAME), str(out)
        )
        return str(out)

    if not image_available():
        raise RuntimeError("OPENAI_API_KEY 미설정 — 배경 이미지 생성 불가")

    from openai import OpenAI  # 기존 의존성

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.images.generate(
        model=_IMAGE_MODEL,
        prompt=_bg_prompt(theme),
        size=_IMAGE_SIZE,
        quality=_IMAGE_QUALITY,
        n=1,
    )
    out.write_bytes(base64.b64decode(resp.data[0].b64_json))
    logger.info("[video] 배경 생성 완료 slug=%s", slug)

    # R2 보존(실패해도 합성은 로컬 파일로 계속).
    try:
        if r2_storage.is_available():
            r2_storage.upload_music_video(str(out), slug, _BG_NAME, content_type="image/png")
    except Exception as e:  # noqa: BLE001
        logger.warning("[video] 배경 R2 저장 실패: %s", e)
    return str(out)


# ── ffmpeg 합성 ──────────────────────────────────────────────────────────
def _build_filter(
    tracks: list[dict], title_kr: str, duration: float, work: Path, viz: str, font: str
) -> str:
    """Ken Burns 배경 + 비주얼라이저 + drawtext(주제·곡 제목) filter_complex 구성.

    textfile 은 work 기준 **상대명**만 쓴다(ffmpeg cwd=work). 절대경로의 '\\'·':' 가
    filtergraph 파싱을 깨뜨리는 걸 회피한다(Windows 호환).
    """
    total_frames = int(duration * FPS) + FPS  # 여유 프레임(루프 reset 회피)

    # 1) 배경 Ken Burns(느린 줌) → 1920x1080.
    bg = (
        f"[0:v]scale={W*1.2:.0f}:{H*1.2:.0f}:force_original_aspect_ratio=increase,"
        f"crop={W*1.2:.0f}:{H*1.2:.0f},"
        f"zoompan=z='min(zoom+0.0004,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={total_frames}:s={W}x{H}:fps={FPS},setsar=1,format=yuv420p[bg];"
    )
    # 2) 오디오 비주얼라이저.
    if viz == "showcqt":
        v = f"[1:a]showcqt=s={W}x220:fps={FPS}[wave];"
    elif viz == "showspectrum":
        v = f"[1:a]showspectrum=s={W}x220:mode=combined:color=intensity:slide=scroll:scale=cbrt[wave];"
    else:  # showwaves(기본)
        v = (
            f"[1:a]showwaves=s={W}x220:mode=cline:rate={FPS}:colors={_VIZ_COLORS}[wave];"
        )
    # 3) 비주얼라이저를 하단에 오버레이.
    overlay = "[bg][wave]overlay=x=0:y=H-h[bgw];"

    # 4) drawtext — 주제 제목(상단 고정) + 곡 제목(전환 구간).
    chain = bg + v + overlay
    prev = "bgw"
    # 주제 제목 — work 기준 상대명(title.txt). 항상 표시.
    (work / "title.txt").write_text(title_kr or "", encoding="utf-8")
    chain += (
        f"[{prev}]drawtext={font}:textfile=title.txt:fontcolor=white:fontsize=54:"
        f"box=1:boxcolor=black@0.45:boxborderw=18:x=(w-text_w)/2:y=56[lbl_t];"
    )
    prev = "lbl_t"

    # 곡 제목 — 컷(duration) 안에서만. start_sec >= duration 인 곡은 스킵,
    # enable 끝은 min(다음 곡 시작, duration) 로 클램프(짧은 컷에서 구간 역전 방지).
    for i, t in enumerate(tracks):
        title = (t.get("title") or "").strip()
        if not title:
            continue
        start = float(t.get("start_sec") or 0.0)
        if start >= duration:
            continue  # 컷 이후 시작 곡은 표시 안 함
        nxt = (
            float(tracks[i + 1].get("start_sec"))
            if i + 1 < len(tracks) and tracks[i + 1].get("start_sec") is not None
            else duration
        )
        end = min(nxt, duration)
        if end <= start:
            continue  # 표시 구간 없음
        tf_name = f"song_{i}.txt"
        (work / tf_name).write_text(title, encoding="utf-8")
        lbl = f"lbl{i}"
        chain += (
            f"[{prev}]drawtext={font}:textfile={tf_name}:fontcolor=white:fontsize=40:"
            f"box=1:boxcolor=black@0.4:boxborderw=12:x=(w-text_w)/2:y=h-th-300:"
            f"enable='between(t,{start:.3f},{end:.3f})'[{lbl}];"
        )
        prev = lbl

    chain += f"[{prev}]format=yuv420p[vout]"
    return chain


def compose_video(
    bg_path: str,
    audio_path: str,
    out_path: str,
    *,
    tracks: list[dict],
    title_kr: str,
    duration: float,
    viz: str | None = None,
) -> str:
    """배경 이미지 + 믹스 오디오 + 비주얼라이저 + 텍스트 → mp4(1920x1080 H.264).

    직접 호출 가능(로컬 bg/audio 경로). make_video 가 R2 연동까지 감싼다.
    """
    _require_ffmpeg()
    viz = viz or os.getenv("MUSIC_VIZ", "showwaves")
    work = Path(tempfile.mkdtemp(prefix="mv_"))
    try:
        # 폰트는 work 로 복사해 상대명 사용. 입력/출력은 절대경로(=CLI 인자, filtergraph
        # 밖이라 OS 무관)로 둔다 — filtergraph 안에는 상대 textfile/fontfile 만 들어간다.
        font = _stage_font(work)
        filt = _build_filter(tracks, title_kr, duration, work, viz, font)
        _run([
            "-loop", "1", "-i", os.path.abspath(str(bg_path)),
            "-i", os.path.abspath(str(audio_path)),
            "-filter_complex", filt,
            "-map", "[vout]", "-map", "1:a",
            "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            os.path.abspath(str(out_path)),
        ], cwd=work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return str(out_path)


def make_video(
    theme: dict,
    mix: dict,
    *,
    seconds: float | None = None,
    viz: str | None = None,
    force_bg: bool = False,
) -> dict:
    """주제 + 믹스 → 배경 생성 → ffmpeg 합성 → mp4 → R2. 영상 메타 반환.

    seconds: 짧은 테스트 컷(앞 N초만). 미지정 시 믹스 전체 길이.
    Returns: {video_id, video_url, duration, slug}
    """
    _require_ffmpeg()
    slug = theme.get("slug") or theme.get("theme_slug") or mix.get("theme_slug") or "untitled"
    mp3_url = mix.get("mp3_url")
    if not mp3_url:
        raise ValueError("mix['mp3_url'] 이 필요합니다.")
    tracks = mix.get("tracks") or []
    title_kr = theme.get("title_kr") or theme.get("title") or slug

    work = Path(tempfile.mkdtemp(prefix="makevid_"))
    try:
        # 오디오·배경 준비.
        audio = work / "mix.mp3"
        _fetch(mp3_url, audio)
        full = _duration(str(audio))
        duration = min(seconds, full) if seconds else full

        bg = work / _BG_NAME
        generate_background(theme, str(bg), force=force_bg)

        video_id = mix.get("mix_id") or "video"
        out = work / f"{video_id}.mp4"
        compose_video(
            str(bg), str(audio), str(out),
            tracks=tracks, title_kr=title_kr, duration=duration, viz=viz,
        )

        video_url = str(out)
        if r2_storage.is_available():
            try:
                video_url = r2_storage.upload_music_video(
                    str(out), slug, f"{video_id}.mp4", content_type="video/mp4"
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("[video] mp4 R2 업로드 실패, 로컬 경로 사용: %s", e)
        else:
            logger.warning("[video] R2 미설정 — mp4 가 로컬에만 있습니다.")

        return {
            "video_id": video_id,
            "video_url": video_url,
            "duration": round(duration, 3),
            "slug": slug,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)
