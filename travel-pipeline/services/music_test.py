"""테스트 영상(#19) — 즉석 10초 Remotion 렌더(유튜브 X, 검토 큐 저장 X).

대시보드 '테스트 영상 생성' 버튼용. make_video 를 거치지 않아(=record_pending·
youtube 미경유) DB·유튜브에 전혀 영향이 없다. 임시 주제 + 합성 오디오(둥근 바가
움직이도록) + 더미 배경으로 영상만 만들어 R2 임시 경로(music-videos/test/{uuid}.mp4)에
올리고 URL 을 돌려준다. Remotion(USE_REMOTION) 우선, 실패 시 ffmpeg 폴백(#18 동일).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from adapters import r2_storage
from services import music_video

logger = logging.getLogger(__name__)

# mood 키 → 테스트 주제(색상 매핑이 의미 있도록 장르/상황 키워드 포함) + 곡 제목 2개.
_PRESETS: dict[str, dict] = {
    "citypop": {
        "genre": "시티팝", "situation": "출근 드라이브", "mood": "상쾌한",
        "title_kr": "테스트 · 시티팝 드라이브",
        "tracks": ["Morning Drive", "City Lights"],
    },
    "cafe": {
        "genre": "재즈", "situation": "카페", "mood": "잔잔한",
        "title_kr": "테스트 · 카페 재즈",
        "tracks": ["Coffee Break", "Afternoon Jazz"],
    },
    "ballad": {
        "genre": "발라드", "situation": "이별", "mood": "쓸쓸한",
        "title_kr": "테스트 · 이별 발라드",
        "tracks": ["비 오는 밤", "그날의 우리"],
    },
    "workout": {
        "genre": "EDM", "situation": "운동", "mood": "동기부여",
        "title_kr": "테스트 · 운동 EDM",
        "tracks": ["Power Up", "Run Faster"],
    },
    "sleep": {
        "genre": "Lo-fi", "situation": "수면 공부", "mood": "차분한",
        "title_kr": "테스트 · 수면 Lo-fi",
        "tracks": ["깊은 밤", "꿈속으로"],
    },
}
_DEFAULT_MOOD = "citypop"


def available_moods() -> list[str]:
    return list(_PRESETS.keys())


def _synth_audio(work: Path, seconds: float) -> Path:
    """둥근 바가 또렷이 움직이도록 3개 배음 + 트레몰로(진폭 LFO) 합성 mp3."""
    out = work / "audio.mp3"
    expr = "0.25*sin(2*PI*196*t)+0.2*sin(2*PI*330*t)+0.16*sin(2*PI*523*t)"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"aevalsrc={expr}:s=44100:d={seconds}:c=stereo",
            "-af", "tremolo=f=6:d=0.7",
            "-c:a", "libmp3lame", "-q:a", "5",
            str(out),
        ],
        check=True, capture_output=True, text=True,
    )
    return out


def _dummy_bg(work: Path) -> Path:
    """더미 배경(짙은 네이비 단색 1920x1080). 실제 썸네일/PLAY LIST 는 운영 영상에서."""
    out = work / "bg.png"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=0x12203a:s=1920x1080:d=1",
            "-frames:v", "1", str(out),
        ],
        check=True, capture_output=True, text=True,
    )
    return out


def render_test(mood: str | None = None, *, seconds: float = 10.0) -> dict:
    """임시 주제로 10초 영상 렌더 → R2 임시 업로드 → {video_url, engine, ...}.

    Remotion(USE_REMOTION on) 우선, 실패/off 면 ffmpeg 폴백. 유튜브·큐 미경유.
    """
    music_video._require_ffmpeg()
    key = (mood or _DEFAULT_MOOD).strip().lower()
    preset = _PRESETS.get(key, _PRESETS[_DEFAULT_MOOD])

    # 곡 2개: 전반부/후반부 → 곡 제목 전환 페이드 확인.
    half = round(seconds / 2.0, 3)
    tracks = [
        {"title": preset["tracks"][0], "start_sec": 0.0},
        {"title": preset["tracks"][1], "start_sec": half},
    ]
    mood_hint = " ".join(
        str(preset.get(k, "")) for k in ("mood", "genre", "situation")
    ).strip()

    work = Path(tempfile.mkdtemp(prefix="mtest_"))
    try:
        audio = _synth_audio(work, seconds)
        bg = _dummy_bg(work)
        out = work / "test.mp4"

        engine = "ffmpeg"
        rendered = False
        if music_video.remotion_enabled():
            try:
                music_video._render_remotion(
                    str(bg), str(audio), str(out),
                    tracks=tracks, mood=mood_hint, duration=seconds,
                )
                rendered = True
                engine = "remotion"
            except Exception as e:  # noqa: BLE001 - Remotion 실패 시 ffmpeg 폴백
                logger.warning("[music-test] Remotion 실패 → ffmpeg 폴백: %s", e)
        if not rendered:
            music_video.compose_video(
                str(bg), str(audio), str(out),
                tracks=tracks, title_kr=preset["title_kr"], duration=seconds,
                static_bg=True,
            )

        if not r2_storage.is_available():
            raise RuntimeError("R2 미설정 — 테스트 영상 업로드 불가")
        name = f"{uuid.uuid4().hex}.mp4"
        video_url = r2_storage.upload_music_video(str(out), "test", name, content_type="video/mp4")
        logger.info("[music-test] 렌더 완료 engine=%s url=%s", engine, video_url)
        return {
            "video_url": video_url,
            "engine": engine,
            "mood": key,
            "duration": seconds,
            "title_kr": preset["title_kr"],
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)
