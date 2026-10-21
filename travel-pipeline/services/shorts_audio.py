"""쇼츠 오디오·영상 분석 — 의존성 추가 없이(ffmpeg + 순수 파이썬) 박자·드롭·후렴·타격 순간을 찾는다.

이미지(python:3.11-slim)에 numpy·librosa 가 없다(librosa 는 의존성 포함 ~400MB). 대신:
- ffmpeg 로 11.025kHz 모노 PCM 디코드 → 11.6ms 단위 RMS 곡선
- onset(에너지 상승) 곡선 → 자기상관으로 BPM 후보 → 박자 격자 일치도로 0.05 BPM·박 위상 보정
- 드롭 = 곡 전체에서 '앞 3초 대비 뒤 3초' 에너지 상승이 가장 큰 지점(박에 맞춤)
- 후렴(쇼츠용 구간) = 드롭 8박 전부터 N초
- 영상 타격 순간 = ffmpeg scdet(프레임 차분) 점수 최대 프레임(예상 구간 안에서만)

합성 곡 검증(0단계): 128 BPM·60초 드롭 → 128.0 / 60.00초, 80 BPM·40초 드롭 → 80.0 / 40.01초,
박 위상 오차 ~20ms(영상 1프레임 33ms 이내). 곡당 1초 미만.
"""

from __future__ import annotations

import array
import math
import subprocess

SR = 11025
HOP = 128
FPS = SR / HOP  # ≈ 86.13 분석 프레임/초
_TIMEOUT = 180


# ── 디코드 · 곡선 ───────────────────────────────────────────────────────
def decode(path: str, *, start: float | None = None, duration: float | None = None) -> array.array:
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", path]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-ac", "1", "-ar", str(SR), "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True, timeout=_TIMEOUT).stdout
    pcm = array.array("h")
    pcm.frombytes(raw[: len(raw) // 2 * 2])
    return pcm


def rms_curve(pcm: array.array) -> list[float]:
    out = []
    for i in range(0, len(pcm) - HOP, HOP):
        s = 0
        for v in pcm[i:i + HOP]:
            s += v * v
        out.append(math.sqrt(s / HOP) / 32768)
    return out


def onset_curve(r: list[float]) -> list[float]:
    le = [math.log(1e-4 + x) for x in r]
    return [0.0] + [max(0.0, le[i] - le[i - 1]) for i in range(1, len(le))]


# ── 박자 ─────────────────────────────────────────────────────────────────
def _autocorr_bpm(on: list[float], lo: float = 70, hi: float = 180) -> float:
    n = len(on)
    m = sum(on) / max(1, n)
    d = [x - m for x in on]
    best = (float("-inf"), lo)
    b = lo
    while b <= hi:
        lag = 60 * FPS / b
        L = int(lag)
        f = lag - L
        s = 0.0
        for i in range(n - L - 1):
            s += d[i] * (d[i + L] * (1 - f) + d[i + L + 1] * f)
        if s > best[0]:
            best = (s, b)
        b += 0.5
    return best[1]


def _comb(on: list[float], bpm: float, start: float) -> float:
    period = 60 * FPS / bpm
    s = 0.0
    t = start
    n = len(on)
    while round(t) < n - 1:
        i = int(round(t))
        s += max(on[i - 1], on[i], on[i + 1]) if i > 0 else on[i]
        t += period
    return s


def _per_point(on: list[float], bpm: float, start: float) -> float:
    """격자점 하나당 평균 onset(격자가 촘촘할수록 점이 많으니 합이 아니라 평균으로 비교)."""
    period = 60 * FPS / bpm
    count = max(1, int((len(on) - 1 - start) // period) + 1)
    return _comb(on, bpm, start) / count


def beat_grid(on: list[float], *, lo: float = 70, hi: float = 180) -> tuple[float, float]:
    """(bpm, 첫 박 시각 초). 자기상관 후보 → ±3 BPM 을 0.05 단위로 격자 일치도 최대화.

    옥타브(절반) 오류 보정: 두 배 격자의 점당 onset 이 원래의 60% 이상이면 두 배 BPM 을 택한다
    (150 BPM 을 75 로 잡는 경우). 박 사이가 비는 곡(쿵쿵따 80 BPM 등)은 두 배 격자 점수가 절반 이하로
    떨어져 그대로 유지된다."""
    bpm, phase = _beat_grid(on, lo, hi)
    double = round(bpm * 2, 2)
    if double <= 190 and _per_point(on, double, phase * FPS) >= 0.6 * _per_point(on, bpm, phase * FPS):
        return double, phase
    return bpm, phase


def _beat_grid(on: list[float], lo: float, hi: float) -> tuple[float, float]:
    b0 = _autocorr_bpm(on, lo, hi)
    best = (float("-inf"), b0, 0.0)
    b = b0 - 3.0
    while b <= b0 + 3.0:
        period = 60 * FPS / b
        for k in range(int(period)):
            s = _comb(on, b, k)
            if s > best[0]:
                best = (s, round(b, 2), k / FPS)
        b += 0.05
    return best[1], best[2]


def snap(t: float, bpm: float, phase: float) -> float:
    beat = 60 / bpm
    return phase + round((t - phase) / beat) * beat


# ── 드롭 · 후렴 ──────────────────────────────────────────────────────────
def _mean(r: list[float], a: int, b: int) -> float:
    a, b = max(0, a), min(len(r), b)
    return sum(r[a:b]) / max(1, b - a)


def find_drop(r: list[float], *, ctx: float = 3.0, edge: float = 5.0) -> float:
    c, e = int(ctx * FPS), int(edge * FPS)
    best = (float("-inf"), 0)
    for i in range(max(c, e), len(r) - max(c, e), 2):
        g = _mean(r, i, i + c) - _mean(r, i - c, i)
        if g > best[0]:
            best = (g, i)
    return best[1] / FPS


def analyze(path: str, *, window: float = 25.0, pre_beats: int = 8) -> dict:
    """곡 1개 → {duration, bpm, phase, drop, chorus_start, chorus_end}. 시각은 모두 초."""
    pcm = decode(path)
    r = rms_curve(pcm)
    on = onset_curve(r)
    bpm, phase = beat_grid(on)
    drop = snap(find_drop(r), bpm, phase)
    dur = len(pcm) / SR
    start = max(0.0, drop - pre_beats * 60 / bpm)
    end = min(dur, start + window)
    return {"duration": round(dur, 2), "bpm": bpm, "phase": round(phase, 3), "drop": round(drop, 3),
            "chorus_start": round(start, 3), "chorus_end": round(end, 3)}


# ── 영상 타격 순간 ───────────────────────────────────────────────────────
def scene_scores(video: str) -> list[tuple[float, float]]:
    """[(시각, scdet 점수)]. 프레임 차분이 클수록 점수↑(섬광·파편·급격한 움직임)."""
    res = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", video, "-vf",
         "scdet=threshold=0,metadata=print:key=lavfi.scd.score:file=-", "-f", "null", "-"],
        capture_output=True, text=True, timeout=_TIMEOUT)
    out, t = [], None
    for line in res.stdout.splitlines():
        if "pts_time:" in line:
            try:
                t = float(line.split("pts_time:")[1].split()[0])
            except ValueError:
                t = None
        elif "lavfi.scd.score=" in line and t is not None:
            try:
                out.append((t, float(line.split("=")[1])))
            except ValueError:
                pass
    return out


def impact_time(video: str, duration: float, *, lo: float = 0.55, hi: float = 0.98,
                min_score: float = 6.0) -> dict:
    """예상 구간(길이의 lo~hi) 안에서 프레임 차분 최대 시각. 약하면 guessed=True(길이의 85%)."""
    scores = [(t, s) for t, s in scene_scores(video) if lo * duration <= t <= hi * duration]
    if scores:
        t, s = max(scores, key=lambda x: x[1])
        if s >= min_score:
            return {"t": round(t, 3), "score": round(s, 2), "guessed": False}
    return {"t": round(0.85 * duration, 3), "score": round(max((s for _, s in scores), default=0.0), 2),
            "guessed": True}


def duration_of(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, timeout=60).stdout.strip()
    return float(out or 0)
