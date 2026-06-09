"""사연 트랙 — TTS 음성 + 싱크 타이밍 (PR-S3).

씬별 narration(국문, S1 출력)을 **라인별로 개별 TTS 생성**해 각 길이를 정확히 확보하고,
고정 쉼(gap_sec)으로 ffmpeg concat 해 전체 나레이션 오디오 1개를 만든다. 라인 길이를
정확히 알기 때문에 silence detection 없이 씬별 타이밍 맵을 산출한다(S4 합성의 기준).

scene_timings 가 S4 핵심 입력:
  - 켄번즈 클립 길이 = 씬 표시 구간 길이
  - 크로스페이드 전환 = 라인 사이 쉼의 '중앙'에 배치
  - 자막 타이밍 = 씬 표시 구간

ffmpeg/ffprobe 가 PATH 에 있어야 한다(영상 파이프라인과 동일 전제).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from adapters import r2_storage
from adapters.tts import get_tts_adapter

logger = logging.getLogger(__name__)


def _require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"{tool} 가 PATH 에 없습니다 — TTS 합성에 ffmpeg 필요.")


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def _to_wav(src: Path, dst: Path) -> None:
    """입력 오디오를 공통 규격(pcm_s16le 44.1kHz mono)으로 정규화 → concat 안전."""
    _run(["ffmpeg", "-y", "-i", str(src), "-ar", "44100", "-ac", "1",
          "-c:a", "pcm_s16le", str(dst)])


def _make_silence(dst: Path, seconds: float) -> None:
    _run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
          "-t", f"{seconds}", "-c:a", "pcm_s16le", str(dst)])


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nokey=1:noprint_wrappers=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def _concat(line_wavs: list[Path], gap: Path, dst: Path) -> None:
    """라인 wav 들을 쉼(gap) 으로 끼워 하나로 concat (스트림 복사)."""
    entries: list[str] = []
    for i, w in enumerate(line_wavs):
        entries.append(f"file '{w.resolve()}'")
        if i < len(line_wavs) - 1:
            entries.append(f"file '{gap.resolve()}'")
    list_path = dst.parent / "concat_list.txt"
    list_path.write_text("\n".join(entries), encoding="utf-8")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
          "-c", "copy", str(dst)])


def _compute_timings(
    indices: list[int], durations: list[float], gap: float, total: float
) -> list[dict]:
    """라인 길이 + 쉼으로 씬별 표시 구간 산출(전환은 쉼 중앙 기준).

    라인 i 시작 L_i: L_0=0, L_i = L_{i-1} + d_{i-1} + gap.
    씬 경계 b_i(씬 i↔i+1) = 라인 i 종료 + gap/2 (= 쉼 중앙).
    씬 i 구간 = [b_{i-1}, b_i), 단 첫 씬 시작=0, 마지막 씬 끝=total.
    """
    n = len(durations)
    starts = [0.0] * n
    cursor = 0.0
    line_start = [0.0] * n
    for i in range(n):
        line_start[i] = cursor
        cursor += durations[i] + (gap if i < n - 1 else 0.0)

    def boundary(i: int) -> float:  # 씬 i 와 i+1 사이 경계(쉼 중앙)
        return line_start[i] + durations[i] + gap / 2.0

    timings: list[dict] = []
    for i in range(n):
        start = 0.0 if i == 0 else boundary(i - 1)
        end = total if i == n - 1 else boundary(i)
        timings.append({
            "index": indices[i],
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
        })
    return timings


def generate_tts(
    job_id: str,
    scenes: list[dict],
    voice_id: str | None = None,
    gap_sec: float = 0.4,
    output_dir: str | None = None,
    progress_cb=None,
) -> dict:
    """씬별 narration → 라인별 TTS + 합친 오디오 + 씬 타이밍 맵.

    Returns:
        {
          "audio_url", "persistent"(R2 여부), "total_duration",
          "voice"(어댑터명),
          "scene_timings": [{index, start, end, duration}]
        }
    """
    _require_ffmpeg()
    narrations = [(s.get("index", i + 1), str(s.get("narration", "")).strip())
                  for i, s in enumerate(scenes)]
    narrations = [(idx, t) for idx, t in narrations if t]
    if not narrations:
        raise ValueError("narration 이 있는 씬이 없습니다.")

    adapter = get_tts_adapter(voice_id)
    out_dir = Path(output_dir or f"output/sayeon/audio/{job_id}")
    out_dir.mkdir(parents=True, exist_ok=True)

    indices: list[int] = []
    durations: list[float] = []
    line_wavs: list[Path] = []
    total = len(narrations)
    for n, (idx, text) in enumerate(narrations, 1):
        if progress_cb:
            progress_cb(int((n - 1) / total * 90), f"라인 {idx} 음성 생성 중...")
        # TTS 원본은 항상 별도 경로(.src.<ext>)로 받는다. Supertone 은 출력이 wav 라
        # 정규화 대상(line_N.wav)과 경로가 겹치면 ffmpeg in==out 으로 거부된다
        # (Edge 는 mp3→wav 라 경로가 달라 안 겹쳤음).
        raw = out_dir / f"line_{idx}.src.{adapter.audio_format}"
        adapter.synthesize(text, str(raw))
        wav = out_dir / f"line_{idx}.wav"
        _to_wav(raw, wav)
        indices.append(idx)
        durations.append(_duration(wav))
        line_wavs.append(wav)

    if progress_cb:
        progress_cb(92, "나레이션 합치는 중...")
    gap_path = out_dir / "gap.wav"
    _make_silence(gap_path, gap_sec)
    combined = out_dir / "narration.wav"
    _concat(line_wavs, gap_path, combined)
    total_duration = _duration(combined)

    timings = _compute_timings(indices, durations, gap_sec, total_duration)

    if progress_cb:
        progress_cb(96, "오디오 R2 업로드 중...")
    audio_url = str(combined)
    persistent = False
    if r2_storage.is_available():
        try:
            audio_url = r2_storage.upload_audio(str(combined), job_id)
            persistent = True
        except Exception as e:  # noqa: BLE001
            logger.warning("나레이션 R2 업로드 실패, 로컬 경로 사용: %s", e)
    else:
        logger.warning("R2 미설정 — 나레이션이 로컬에만 있습니다(S4 는 R2 권장).")

    if progress_cb:
        progress_cb(100, "완료")
    return {
        "audio_url": audio_url,
        "persistent": persistent,
        "total_duration": round(total_duration, 3),
        "voice": adapter.name,
        "scene_timings": timings,
    }
