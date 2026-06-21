"""음악 마스터링 (Rooftop Music) — 2-pass loudnorm 으로 -14 LUFS 통일.

#1 에서 R2 에 영구저장된 원본 곡(music-masters/{slug}/{audio_id}.mp3)을 받아
ffmpeg loudnorm 2-pass(측정 → 적용)로 라우드니스를 통일하고 마스터본을
music-masters/{slug}/mastered/{audio_id}.mp3 에 올린다(멱등 — 이미 있으면 skip).

타깃: I=-14 LUFS, TP=-1.0 dBTP, LRA=11 (유튜브 음악 기준). 출력 mp3 320k.
EQ 레퍼런스 매칭(Matchering)은 이번 범위 밖.

ffmpeg 헬퍼는 백곰 엔진(sayeon_*)과 결합하지 않도록 이 모듈에 소량 복제한다
(subprocess 직접 호출 — ffmpeg/ffprobe 는 시스템 바이너리 가정, 백곰과 동일 전제).
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

from adapters import r2_storage
from services import music_store

logger = logging.getLogger(__name__)

# 마스터 타깃 — 측정·적용 패스 공통.
TARGET_I = -14.0
TARGET_TP = -1.0
TARGET_LRA = 11.0
_MP3_BITRATE = "320k"


# ── ffmpeg 헬퍼(디커플링 복제) ───────────────────────────────────────────
def _require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"{tool} 가 PATH 에 없습니다 — 마스터링에 ffmpeg 필요.")


def _run(args: list[str]) -> str:
    """ffmpeg 실행. stderr 를 반환(loudnorm JSON 측정값이 stderr 로 나온다)."""
    result = subprocess.run(
        ["ffmpeg", "-y", *args], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg 오류:\n{result.stderr[-2000:]}")
    return result.stderr


def _fetch(url_or_path: str, dest: Path) -> None:
    """http(s) URL 이면 다운로드, 로컬 경로면 복사."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if url_or_path.startswith(("http://", "https://")):
        with httpx.Client(timeout=180.0, follow_redirects=True) as client:
            resp = client.get(url_or_path)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
    else:
        shutil.copy(url_or_path, dest)


# ── 2-pass loudnorm ──────────────────────────────────────────────────────
def _measure(src: Path) -> dict:
    """패스1: loudnorm 측정값(JSON)을 얻는다. stderr 끝의 JSON 블록을 파싱."""
    af = (
        f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json"
    )
    stderr = _run(["-i", str(src), "-af", af, "-f", "null", "-"])
    # stderr 끝부분의 마지막 {...} JSON 블록만 추출.
    matches = re.findall(r"\{[^{}]*\}", stderr, re.DOTALL)
    if not matches:
        raise RuntimeError("loudnorm 측정값(JSON)을 파싱하지 못했습니다.")
    return json.loads(matches[-1])


def _apply(src: Path, dst: Path, measured: dict) -> None:
    """패스2: 측정값을 넣어 선형 정규화 후 mp3 320k 로 인코딩."""
    af = (
        f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}"
        f":measured_I={measured['input_i']}"
        f":measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}"
        f":measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}"
        ":linear=true:print_format=summary"
    )
    _run([
        "-i", str(src),
        "-af", af,
        "-ar", "44100",
        "-c:a", "libmp3lame", "-b:a", _MP3_BITRATE,
        str(dst),
    ])


def master_file(src: Path, dst: Path) -> Path:
    """로컬 mp3 → 2-pass loudnorm 마스터본 mp3(로컬). 배관/검증용 단위 함수."""
    _require_ffmpeg()
    measured = _measure(src)
    _apply(src, dst, measured)
    return dst


def master_track(
    theme_slug: str,
    track: dict,
    *,
    force: bool = False,
) -> dict:
    """곡 1개를 마스터링해 R2 mastered/ 에 올린다(멱등).

    track: music_tracks 행({audio_id, r2_key, ...}) 또는 최소 {audio_id, r2_key}.
    force=False 면 마스터본이 이미 있을 때 업로드를 건너뛴다.
    Returns: {audio_id, mastered_key, mastered_url, skipped}
    """
    _require_ffmpeg()
    audio_id = track.get("audio_id") or track.get("id") or ""
    if not audio_id:
        raise ValueError("master_track: audio_id 가 없습니다.")

    mastered_key = r2_storage.mastered_music_key(theme_slug, audio_id)
    if not force and r2_storage.mastered_music_exists(theme_slug, audio_id):
        logger.info("[master] 이미 존재 — 스킵 key=%s", mastered_key)
        return {
            "audio_id": audio_id,
            "mastered_key": mastered_key,
            "mastered_url": r2_storage.mastered_music_url(theme_slug, audio_id),
            "skipped": True,
        }

    if not r2_storage.is_available():
        raise RuntimeError("R2 미설정 — 마스터본을 영구 저장할 수 없습니다.")

    # 원본 소스: r2_key(우선) → 없으면 음악 키 규칙으로 폴백.
    src_key = track.get("r2_key") or r2_storage.music_key(theme_slug, audio_id)
    tmpdir = Path(tempfile.mkdtemp(prefix="master_"))
    try:
        raw = tmpdir / f"{audio_id}.mp3"
        r2_storage.download_music_object(src_key, str(raw))
        mastered = tmpdir / f"{audio_id}.mastered.mp3"
        master_file(raw, mastered)
        url = r2_storage.upload_mastered_music(str(mastered), theme_slug, audio_id)
        logger.info("[master] R2 저장 OK key=%s", mastered_key)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return {
        "audio_id": audio_id,
        "mastered_key": mastered_key,
        "mastered_url": url,
        "skipped": False,
    }


def master_theme(
    theme_slug: str,
    tracks: list[dict] | None = None,
    *,
    force: bool = False,
) -> list[dict]:
    """테마의 모든(또는 주어진) 곡을 마스터링한다. 결과 리스트 반환.

    tracks 미지정 시 music_tracks 에서 status=SUCCESS 곡을 조회한다.
    """
    rows = tracks if tracks is not None else music_store.list_tracks(theme_slug)
    results: list[dict] = []
    for row in rows:
        try:
            results.append(master_track(theme_slug, row, force=force))
        except Exception as e:  # noqa: BLE001 - 곡 1개 실패가 전체를 막지 않게
            logger.warning(
                "[master] 곡 마스터 실패(audio_id=%s): %s",
                row.get("audio_id") or row.get("id"), e,
            )
    return results
