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


# 라우드니스 타깃(유튜브 권장): I=-14 LUFS, TP=-1.5 dBTP, LRA=11.
# 클립별 1-pass 로 적용한다 — 클립 간 음량 편차가 원인이므로 'concat 전 정규화'가 핵심.
# (2-pass 가 측정상 더 정밀하지만 라인 수×2 의 ffmpeg 호출이 추가되고, 짧은 발화
# 클립에는 1-pass 로 충분해 처리 시간을 우선했다.)
_LOUDNORM = "loudnorm=I=-14:TP=-1.5:LRA=11"


def _to_wav(src: Path, dst: Path) -> None:
    """입력 오디오를 공통 규격(pcm_s16le 44.1kHz mono) + 타깃 라우드니스로 정규화.

    이 단계는 원래도 재인코딩이라 loudnorm 추가에 별도 패스가 들지 않으며,
    여기서 클립별 음량을 맞춰두면 이후 concat 은 -c copy(스트림 복사)를 유지할
    수 있다(PR #40 OOM 해결책과 충돌 없음).
    """
    _run(["ffmpeg", "-y", "-i", str(src), "-af", _LOUDNORM,
          "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(dst)])


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


# 무음 판정 임계치(평균 음량). 정상 발화는 보통 -30~-14 dB, 완전 무음은 -inf/-91 dB.
_SILENCE_DB = -50.0


def _mean_volume(path: Path) -> float | None:
    """ffmpeg volumedetect 로 평균 음량(dB)을 읽는다. 측정 실패 시 None.

    완전 무음(-inf)은 매우 작은 값으로 떨어지므로 무음/누락 클립 판별에 쓴다.
    """
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    for line in proc.stderr.splitlines():
        if "mean_volume:" in line:
            try:
                return float(line.split("mean_volume:")[1].strip().split()[0])
            except (ValueError, IndexError):
                return None
    return None


def _check_line_audio(idx: int, wav: Path, duration: float) -> str | None:
    """씬 TTS 클립의 누락/무음을 검증한다. 문제 있으면 사유 문자열, 정상이면 None.

    '자막은 있는데 음성이 없는 구간'을 합성 전에 잡기 위함.
    """
    if not wav.exists():
        return "클립 파일 없음(누락)"
    if duration < 0.05:
        return f"길이 0 의심(dur={duration:.3f}s)"
    mv = _mean_volume(wav)
    if mv is None:
        return "평균 음량 측정 실패"
    if mv < _SILENCE_DB:
        return f"무음 의심(mean_volume={mv:.1f}dB)"
    return None


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
    silent_scenes: list[int] = []  # 무음/누락 클립 씬 번호(자막만 있고 음성 없는 구간)
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
        dur = _duration(wav)
        # 합성 전 검증: 자막은 있는데 음성이 없는(무음/누락) 클립을 로그로 명시.
        problem = _check_line_audio(idx, wav, dur)
        if problem:
            silent_scenes.append(idx)
            logger.warning(
                "씬 %s TTS 클립 이상 — %s | narration=%r", idx, problem, text[:40]
            )
        indices.append(idx)
        durations.append(dur)
        line_wavs.append(wav)

    if silent_scenes:
        logger.warning(
            "TTS 무음/누락 의심 씬 %d개: %s (자막만 있고 음성 없는 구간일 수 있음 — "
            "TTS 프로바이더/voice_id/텍스트 확인 권장)",
            len(silent_scenes), silent_scenes,
        )

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
        "silent_scenes": silent_scenes,  # 무음/누락 의심 씬(자막만 있고 음성 없는 구간)
    }
