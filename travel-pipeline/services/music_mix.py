"""롱폼 믹스 (Rooftop Music) — 마스터본 트랙들을 크로스페이드로 한 곡처럼 잇기.

한 테마의 마스터본(music-masters/{slug}/mastered/{audio_id}.mp3)들을 받아
  1) 목표 길이까지 트랙 선택(기본 30~60분, 인자로 조절)
  2) 셔플 — 형제곡(같은 task_id)을 서로 멀리 배치
  3) acrossfade(기본 2s) 페어와이즈 concat → 롱폼 mp3
한 뒤 R2 에 올린다:
  - 믹스 mp3 → music-mixes/{slug}/{mix_id}.mp3
  - 오프셋 메타 JSON → music-mixes/{slug}/{mix_id}.json (곡 순서 + 시작 초 + 제목, #3 챕터/자막용)

신규 DB 테이블 없음(메타는 JSON). ffmpeg 헬퍼는 백곰 엔진과 결합하지 않도록
이 모듈에 소량 복제한다(subprocess 직접 호출).
"""

from __future__ import annotations

import json
import logging
import random
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from adapters import r2_storage
from services import music_store

logger = logging.getLogger(__name__)

CROSSFADE_SEC = 2.0           # 곡 사이 크로스페이드 길이(초)
DEFAULT_MINUTES = 45          # 기본 목표 길이(분) — 30~60 사이
_MP3_BITRATE = "320k"


# ── ffmpeg 헬퍼(디커플링 복제) ───────────────────────────────────────────
def _require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"{tool} 가 PATH 에 없습니다 — 믹스에 ffmpeg 필요.")


def _run(args: list[str]) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", *args], capture_output=True, text=True
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


# ── 셔플(형제곡 분산) ────────────────────────────────────────────────────
def _shuffle_spread(tracks: list[dict], seed: int | None = None) -> list[dict]:
    """형제곡(같은 task_id)이 서로 인접하지 않도록 라운드로빈으로 펼친다.

    task_id 별 버킷으로 나눠 셔플하고, 매 단계 '직전과 다른 task_id 중 남은 곡이
    가장 많은 버킷'에서 하나씩 뽑는다. 한 task_id 만 남으면 어쩔 수 없이 연속 배치.
    """
    rnd = random.Random(seed)
    buckets: dict[str, list[dict]] = {}
    for t in tracks:
        buckets.setdefault(t.get("task_id") or "_", []).append(t)
    for b in buckets.values():
        rnd.shuffle(b)

    order: list[dict] = []
    last_tid: str | None = None
    while any(buckets.values()):
        candidates = [tid for tid, b in buckets.items() if b and tid != last_tid]
        if not candidates:  # 남은 게 직전 task_id 뿐 → 연속 허용
            candidates = [tid for tid, b in buckets.items() if b]
        # 남은 곡이 많은 버킷 우선(동률은 랜덤) — 한쪽이 몰려 끝에서 뭉치는 걸 완화.
        rnd.shuffle(candidates)
        tid = max(candidates, key=lambda k: len(buckets[k]))
        order.append(buckets[tid].pop())
        last_tid = tid
    return order


def _select_for_target(
    tracks: list[dict], target_sec: float, *, seed: int | None = None
) -> list[dict]:
    """목표 길이를 채울 때까지 트랙을 고른다(셔플 후 누적). 곡이 모자라면 있는 만큼.

    duration 은 music_tracks 행 값(초)을 쓰되 없으면 평균 180s 로 가정(선택용 근사,
    실제 오프셋은 마스터본 ffprobe 로 보정).
    """
    spread = _shuffle_spread(tracks, seed=seed)
    selected: list[dict] = []
    acc = 0.0
    for t in spread:
        selected.append(t)
        try:
            acc += float(t.get("duration") or 0) or 180.0
        except (TypeError, ValueError):
            acc += 180.0
        if acc >= target_sec:
            break
    return selected


# ── acrossfade 페어와이즈 concat ─────────────────────────────────────────
def _acrossfade_pair(acc: Path, nxt: Path, out: Path, cf: float) -> None:
    _run([
        "-i", str(acc),
        "-i", str(nxt),
        "-filter_complex",
        f"[0][1]acrossfade=d={cf}:c1=tri:c2=tri[a]",
        "-map", "[a]",
        "-ar", "44100", "-c:a", "libmp3lame", "-b:a", _MP3_BITRATE,
        str(out),
    ])


def _concat_crossfade(
    files: list[Path], cf: float, work: Path
) -> tuple[Path, list[float]]:
    """파일들을 acrossfade 로 순차(2개씩) 합친다. (최종경로, 각 곡 시작초) 반환.

    페어와이즈라 피크 메모리가 입력 2개로 제한된다(백곰 xfade 체인과 동일 전략).
    시작초는 실제 누적 길이로 계산: start_k = running - cf, running += dur_k - cf.
    """
    durs = [_duration(f) for f in files]
    starts: list[float] = []
    running = 0.0
    for k, d in enumerate(durs):
        if k == 0:
            starts.append(0.0)
            running = d
        else:
            starts.append(round(max(0.0, running - cf), 3))
            running = running + d - cf

    if len(files) == 1:
        only = work / "mix.mp3"
        shutil.copy(files[0], only)
        return only, starts

    acc = files[0]
    for k in range(1, len(files)):
        out = work / ("mix.mp3" if k == len(files) - 1 else f"acc_{k}.mp3")
        _acrossfade_pair(acc, files[k], out, cf)
        acc = out
    return acc, starts


def build_mix(
    theme_slug: str,
    tracks: list[dict] | None = None,
    *,
    minutes: float = DEFAULT_MINUTES,
    crossfade: float = CROSSFADE_SEC,
    seed: int | None = None,
    mix_id: str | None = None,
    lyrics_by_id: dict[str, str] | None = None,
) -> dict:
    """테마의 마스터본들로 롱폼 믹스 mp3 + 오프셋 JSON 을 만들어 R2 에 올린다.

    tracks 미지정 시 music_tracks(status=SUCCESS)를 조회한다. 각 곡의 마스터본을
    R2 에서 받아 acrossfade 로 잇는다(마스터본이 없으면 그 곡은 건너뜀).
    lyrics_by_id(선택): audio_id→가사. 주어지면 오프셋 JSON 의 각 곡에 가사를
    함께 실어 #4 자막 동기화에 쓴다.
    Returns: {mix_id, mp3_url, json_url, track_count, total_duration, tracks:[메타]}
    """
    lyrics_by_id = lyrics_by_id or {}
    _require_ffmpeg()
    if not r2_storage.is_available():
        raise RuntimeError("R2 미설정 — 믹스를 저장할 수 없습니다.")

    rows = tracks if tracks is not None else music_store.list_tracks(theme_slug)
    if not rows:
        raise ValueError(f"테마 '{theme_slug}' 에 믹스할 곡이 없습니다.")

    # #40 곡 전부 사용 — 영상 길이 = 곡 총 길이(자르지 않음). minutes 상한 제거(target_sec=inf).
    # 1~2곡은 기존에도 minutes(10분) 미달이라 전곡 사용했으므로 동작 동일(회귀 0). 3곡↑부터 길어짐.
    selected = _select_for_target(rows, float("inf"), seed=seed)
    mix_id = mix_id or f"mix_{time.strftime('%Y%m%d_%H%M%S')}"

    work = Path(tempfile.mkdtemp(prefix="mix_"))
    try:
        # 선택 곡들의 마스터본을 받는다(없으면 건너뜀). 메타와 파일 순서를 일치시킨다.
        files: list[Path] = []
        meta_tracks: list[dict] = []
        for t in selected:
            audio_id = t.get("audio_id") or t.get("id") or ""
            if not audio_id:
                continue
            if not r2_storage.mastered_music_exists(theme_slug, audio_id):
                logger.warning("[mix] 마스터본 없음 — 건너뜀 audio_id=%s", audio_id)
                continue
            dst = work / f"{audio_id}.mp3"
            r2_storage.download_music_object(
                r2_storage.mastered_music_key(theme_slug, audio_id), str(dst)
            )
            files.append(dst)
            entry = {"audio_id": audio_id, "title": t.get("title") or ""}
            # 가사: 인자(lyrics_by_id) 우선, 없으면 트랙 행에 실린 lyrics 사용.
            lyric = lyrics_by_id.get(audio_id) or t.get("lyrics")
            if lyric:
                entry["lyrics"] = lyric
            meta_tracks.append(entry)

        if not files:
            raise ValueError(
                f"테마 '{theme_slug}' 에 마스터본이 없습니다 — 먼저 마스터링하세요."
            )

        mixed, starts = _concat_crossfade(files, crossfade, work)
        total = round(_duration(mixed), 3)

        # 오프셋 메타(곡 순서 + 시작 초 + 제목) — #3 챕터/자막용.
        for i, m in enumerate(meta_tracks):
            m["order"] = i
            m["start_sec"] = starts[i]
        meta = {
            "mix_id": mix_id,
            "theme_slug": theme_slug,
            "crossfade_sec": crossfade,
            "total_duration": total,
            "track_count": len(meta_tracks),
            "tracks": meta_tracks,
        }
        meta_path = work / f"{mix_id}.json"
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # R2 업로드(mp3 + json). R2 저장 완료가 산출물의 진실 출처.
        mp3_url = r2_storage.upload_music_mix(str(mixed), theme_slug, mix_id, ext="mp3")
        json_url = r2_storage.upload_music_mix(
            str(meta_path), theme_slug, mix_id,
            ext="json", content_type="application/json",
        )
        logger.info(
            "[mix] 완료 mix_id=%s 곡=%d 길이=%.1fs", mix_id, len(meta_tracks), total
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)

    return {
        "mix_id": mix_id,
        "mp3_url": mp3_url,
        "json_url": json_url,
        "track_count": len(meta_tracks),
        "total_duration": total,
        "tracks": meta_tracks,
    }
