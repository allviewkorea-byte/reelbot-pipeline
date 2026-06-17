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
import tempfile
from pathlib import Path

import httpx

from adapters import r2_storage
from services.sayeon_bgm import fetch_bgm

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
    """클립들을 0.6s 크로스페이드로 이어붙인다(재인코딩). 클립 1개면 그대로 복사.

    Railway 메모리 절감을 위해 클립 N개(씬 길이에 따라 가변)를 한 그래프에 동시에
    넣지 않고 '순차 2개씩' 합친다: 누적본(acc) + 다음 클립을 ffmpeg 1회로 xfade →
    중간 파일, 마지막까지 반복. 각 단계 입력이 2개뿐이라 피크 메모리가 크게 줄어든다.

    누적 길이/전환 오프셋은 '한 그래프' 방식과 동일하게 계산하므로(offset = 누적길이 -
    XFADE, 누적길이 += 다음.dur - XFADE) 최종 길이·크로스페이드 위치는 기존과 동일하다.
    """
    n = len(clips)
    if n == 1:
        shutil.copy(cwd / clips[0].name, cwd / out.name)
        return

    tmp = Path(tempfile.mkdtemp(prefix="xfade_", dir=str(cwd)))
    rel = tmp.name  # cwd 기준 상대 경로
    try:
        acc_name = clips[0].name      # 현재 누적본(cwd 기준 상대 경로)
        acc_dur = clip_durs[0]
        for k in range(1, n):
            offset = round(acc_dur - XFADE, 3)
            is_last = k == n - 1
            out_name = out.name if is_last else f"{rel}/acc_{k}.mp4"
            _run([
                "-i", acc_name,
                "-i", clips[k].name,
                "-filter_complex",
                f"[0][1]xfade=transition=fade:duration={XFADE}:offset={offset}[v]",
                "-map", "[v]",
                "-c:v", "libx264", "-preset", PRESET, "-crf", "20", "-threads", THREADS,
                "-pix_fmt", "yuv420p", "-r", str(FPS),
                out_name,
            ], cwd=cwd)
            acc_name = out_name
            acc_dur = acc_dur + clip_durs[k] - XFADE
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _ass_time(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t - h * 3600 - m * 60
    return f"{h}:{m:02d}:{s:05.2f}"


# 감정 피크 씬 강조 색(ASS 는 BGR 표기). 노랑/빨강으로 핵심 단어를 칠한다.
_EMPHASIS_DEFAULT = "&H00F0FF&"   # 평소 강조(노랑톤) — 기존 동작 유지
_EMOTION_COLOR = {
    "shock": "&H00FFFF&",    # 노랑
    "sadness": "&H00FFFF&",  # 노랑
    "anger": "&H0000FF&",    # 빨강
}
_PEAK_EMOTIONS = set(_EMOTION_COLOR)  # 감정 피크 씬(shock/anger/sadness)
_PEAK_FONTSIZE = 100  # 기본 90pt + 10pt
_FADE = "\\fad(150,100)"  # 자막 페이드 인/아웃

# emotion 별 핵심 키워드(자막에서 찾아 색칠). 오탐을 줄이려 2자 이상 구체어만.
_EMOTION_KEYWORDS = {
    "shock": ("충격", "소름", "깜짝", "믿기지", "설마", "발견", "들켰", "기절"),
    "anger": ("배신", "어이없", "뻔뻔", "황당", "화가", "화났", "용서", "분노"),
    "sadness": ("눈물", "울컥", "허탈", "무너", "미안", "그리워", "외로", "후회"),
}


def _emphasis_keywords(text: str, highlight: str, emotion: str) -> list[str]:
    """자막에서 색칠할 핵심 키워드 선정. highlight 우선, 없으면 감정 사전에서 추출."""
    if highlight and highlight in text:
        return [highlight]
    keywords: list[str] = []
    for kw in _EMOTION_KEYWORDS.get(emotion, ()):  # 감정 피크 씬만 사전 매칭
        if kw in text and kw not in keywords:
            keywords.append(kw)
        if len(keywords) >= 2:  # 최대 2개
            break
    return keywords


def _ass_text(subtitle: str, highlight: str, emotion: str = "") -> str:
    """자막 텍스트. 핵심 키워드를 감정별 색(노랑/빨강)으로 감싼다(§4 + PR⑨).

    emotion 이 감정 피크(shock/anger/sadness)면 해당 색으로 강조하고, 그 외에는
    기존처럼 highlight 구만 노랑톤으로 칠한다. 페이드·폰트 확대는 줄 단위로
    _build_ass 에서 얹는다(여기서는 인라인 색만).
    """
    text = subtitle.strip()
    emo = (emotion or "").strip().lower()
    color = _EMOTION_COLOR.get(emo, _EMPHASIS_DEFAULT)
    for kw in _emphasis_keywords(text, highlight, emo):
        text = text.replace(kw, f"{{\\c{color}}}{kw}{{\\c&HFFFFFF&}}", 1)
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
        # 자막 확대(74→90, 외곽선5→6·그림자3→4)로 가독성 ↑. 하단 중앙(Alignment=2),
        # MarginV 340→400 으로 9:16 안전영역(하단 진행바·버튼)을 피해 위로 띄운다.
        # WrapStyle=0 로 긴 문장은 2줄로 자동 래핑(MarginL/R=40 폭 제한).
        f"Style: Default,{_FONT},90,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "1,0,0,0,100,100,0,0,1,6,4,2,40,40,400,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    lines = [header]
    for it in items:
        emotion = str(it.get("emotion", "")).strip().lower()
        text = _ass_text(it.get("subtitle", ""), it.get("highlight", ""), emotion)
        if not text:
            continue
        # 줄 단위 오버라이드: 페이드 인/아웃 + 감정 피크 씬은 폰트 10pt 확대.
        override = _FADE + (f"\\fs{_PEAK_FONTSIZE}" if emotion in _PEAK_EMOTIONS else "")
        lines.append(
            f"Dialogue: 0,{_ass_time(it['start'])},{_ass_time(it['end'])},"
            f"Default,,0,0,0,,{{{override}}}{text}\n"
        )
    ass_path.write_text("".join(lines), encoding="utf-8")


# 라우드니스 타깃(유튜브 권장): I=-14 LUFS, TP=-1.5 dBTP, LRA=11.
_LOUDNORM = "loudnorm=I=-14:TP=-1.5:LRA=11"

# BGM 믹싱 파라미터(튜닝 1줄). 빽빽한 90초 나레이션에 묻히지 않게 배경으로 살린다.
# 게인↑(-19→-15) + 덕킹 완화(ratio 6→4, release 400→300ms) = BGM 더 잘 들리되 목소리 우선.
_BGM_GAIN_DB = -15          # BGM 베이스 게인(나레이션 대비). 목소리가 메인, BGM 은 배경.
_BGM_DUCK_RATIO = 4         # 사이드체인 압축비(목소리 나올 때 BGM 눌림 정도). 낮을수록 덜 눌림.
_BGM_DUCK_RELEASE_MS = 300  # 목소리 멎은 뒤 BGM 회복 시간(ms). 짧을수록 갭에서 빨리 살아남.


def _prepare_audio_track(audio: Path, cwd: Path, bgm: Path | None = None) -> Path:
    """오디오 체인(분리 함수) — 최종 나레이션 트랙 정규화(+선택적 BGM 덕킹).

    TTS 단계(sayeon_tts)가 클립별 loudnorm 을 이미 적용하므로 그 산출물에는 거의
    무변화(안전망)지만, 외부/과거 audio_url 입력도 동일 타깃으로 맞춰준다.
    오디오 전용 1-pass 재인코딩이라 메모리 부담이 거의 없고 영상 스트림은 일절
    건드리지 않는다.

    bgm 이 주어지면 나레이션 아래에 배경음악을 덕킹해 깐다:
      - BGM 을 나레이션 길이만큼 무한 루프(-stream_loop)로 채우고
      - 베이스 게인 _BGM_GAIN_DB(-15dB)로 낮춘 뒤
      - 나레이션을 사이드체인 키로 sidechaincompress(목소리가 나올 때 BGM 눌림, ratio/release 완화)
      - amix(normalize=0)로 합치고 전체를 -14 LUFS 로 재정규화.
    """
    out = cwd / "narration_norm.wav"
    if bgm is None:
        _run([
            "-i", audio.name,
            "-af", _LOUDNORM,
            "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le",
            out.name,
        ], cwd=cwd)
        return out

    # 나레이션을 둘로 분기(asplit): 하나는 믹스용, 하나는 사이드체인 키용.
    # ffmpeg 는 라벨 링크를 한 번만 연결할 수 있어 분기가 필요하다.
    filt = (
        "[0:a]aresample=44100,aformat=channel_layouts=mono,asplit=2[voice][vkey];"
        f"[1:a]aresample=44100,aformat=channel_layouts=mono,volume={_BGM_GAIN_DB}dB[bgmv];"
        "[bgmv][vkey]sidechaincompress="
        f"threshold=0.05:ratio={_BGM_DUCK_RATIO}:attack=20:release={_BGM_DUCK_RELEASE_MS}[bgmduck];"
        "[voice][bgmduck]amix=inputs=2:duration=first:"
        "dropout_transition=0:normalize=0[mix];"
        f"[mix]{_LOUDNORM}[out]"
    )
    _run([
        "-i", audio.name,
        # BGM 을 나레이션 길이만큼 루프(amix duration=first 가 길이를 나레이션에 맞춤).
        "-stream_loop", "-1", "-i", bgm.name,
        "-filter_complex", filt,
        "-map", "[out]",
        "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le",
        out.name,
    ], cwd=cwd)
    return out


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
    bgm_mood: str | None = None,
) -> dict:
    """씬 이미지 + 타이밍 + 자막 + 음성 → 완성 mp4. Returns {"video_url", ...}.

    bgm_mood(emotional|suspense|hopeful)가 주어지면 해당 분위기 BGM 한 곡을 R2 에서
    무작위로 받아 나레이션 아래에 덕킹해 깐다(없으면/실패하면 BGM 없이 진행).
    """
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
    # 분위기 BGM 선택(R2). 실패해도 None 으로 BGM 없이 진행(파이프라인 안 멈춤).
    bgm_local = fetch_bgm(bgm_mood, out_dir) if bgm_mood else None
    # 오디오 체인: (BGM 덕킹 +) 라우드니스 정규화(-14 LUFS). 영상 스트림은 안 건드린다.
    audio_local = _prepare_audio_track(audio_local, out_dir, bgm=bgm_local)

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
            "emotion": scene.get("emotion", ""),  # 감정 피크 씬 자막 강조용
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
