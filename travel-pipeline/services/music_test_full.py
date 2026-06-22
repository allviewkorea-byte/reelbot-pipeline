"""1곡 풀 테스트(#25) — 즉석 주제 1개 → 진짜 음원 1곡 → 가사·viz_spec → Remotion 풀 렌더.

빠른 10초 테스트(music_test)와 달리 **실제 제작 파이프라인**(music_produce.produce: 가사
GPT → suno 보컬 → 마스터 → 믹스)을 1곡으로 돌려 진짜 음원·가사가 들어간 영상을 만든다.
단 **DB 영구 저장 X**(make_video persist=False → record_pending 미경유), **유튜브 X**.

수 분 걸리므로 BackgroundTasks 로 비동기 실행 + 인메모리 job 상태 폴링. 동시 1개 제한.
JobManager 는 인메모리(재시작 시 소실) — 테스트 용도라 영속화 불필요.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

# mood → 실제 제작용 주제(스타일·톤 포함). genre/situation/mood/title 은 music_test 와 일관.
_THEMES: dict[str, dict] = {
    "citypop": {
        "genre": "시티팝", "situation": "출근 드라이브", "mood": "상쾌한",
        "title_kr": "테스트 · 시티팝 드라이브",
        "style_prompt": "city pop, 80s Japanese citypop, warm analog, lush chords, nostalgic",
        "lyric_tone": "상쾌하고 자유로운 아침 드라이브",
    },
    "cafe": {
        "genre": "재즈", "situation": "카페", "mood": "잔잔한",
        "title_kr": "테스트 · 카페 재즈",
        "style_prompt": "smooth jazz, cafe lounge, mellow piano, relaxed, warm",
        "lyric_tone": "잔잔하고 따뜻한 오후의 커피",
    },
    "ballad": {
        "genre": "발라드", "situation": "이별", "mood": "쓸쓸한",
        "title_kr": "테스트 · 이별 발라드",
        "style_prompt": "korean ballad, emotional piano, sad strings, tender",
        "lyric_tone": "쓸쓸한 이별의 밤",
    },
    "workout": {
        "genre": "EDM", "situation": "운동", "mood": "동기부여",
        "title_kr": "테스트 · 운동 EDM",
        "style_prompt": "energetic EDM, motivational, driving beat, uplifting",
        "lyric_tone": "힘차고 동기부여되는",
    },
    "sleep": {
        "genre": "Lo-fi", "situation": "수면 공부", "mood": "차분한",
        "title_kr": "테스트 · 수면 Lo-fi",
        "style_prompt": "lofi chill, calm, soft piano, ambient, sleepy",
        "lyric_tone": "나른하고 평온한 밤",
    },
}
_DEFAULT_MOOD = "citypop"

# 진행 단계(프론트 표시용 한국어).
_STEPS = ["대기", "주제", "음원·가사", "렌더", "완료"]

# 인메모리 job 저장소 + 동시 1개 제한 락.
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
_active_job: str | None = None


def available_moods() -> list[str]:
    return list(_THEMES.keys())


def _build_theme(mood: str) -> dict:
    preset = _THEMES.get(mood, _THEMES[_DEFAULT_MOOD])
    return {
        "slug": f"testfull_{uuid.uuid4().hex[:12]}",
        "title_kr": preset["title_kr"],
        "genre": preset["genre"],
        "situation": preset["situation"],
        "mood": preset["mood"],
        "type": "vocal",
        "style_prompt": preset["style_prompt"],
        "lyric_tone": preset["lyric_tone"],
        "track_count": 1,
    }


def start(mood: str | None = None) -> dict:
    """풀 테스트 1개 시작(동시 1개 제한). {ok, job_id} 또는 {ok:False, error, busy_job}."""
    global _active_job
    key = (mood or _DEFAULT_MOOD).strip().lower()
    with _LOCK:
        if _active_job and _JOBS.get(_active_job, {}).get("status") == "running":
            return {"ok": False, "error": "이미 풀 테스트가 진행 중입니다. 완료 후 다시 시도하세요.", "busy_job": _active_job}
        job_id = uuid.uuid4().hex
        _JOBS[job_id] = {
            "job_id": job_id, "status": "running", "step": "대기",
            "mood": key, "video_url": None, "error": None,
            "created_at": time.time(),
        }
        _active_job = job_id
    return {"ok": True, "job_id": job_id}


def get_status(job_id: str) -> dict | None:
    job = _JOBS.get(job_id)
    if not job:
        return None
    return {k: job[k] for k in ("job_id", "status", "step", "mood", "video_url", "error")}


def run(job_id: str) -> None:
    """백그라운드 실행체 — produce(1곡) → make_video(persist=False) → video_url."""
    global _active_job
    job = _JOBS.get(job_id)
    if not job:
        return

    def _step(name: str) -> None:
        job["step"] = name
        logger.info("[music-fulltest] job=%s step=%s", job_id, name)

    work: Path | None = None
    try:
        from services import music_produce, music_test, music_video, music_viz_analyzer

        theme = _build_theme(job["mood"])
        slug = theme["slug"]

        _step("음원·가사")
        # 실제 제작: 가사(GPT) → suno 보컬 1곡 → 마스터 → 믹스(3~4분).
        result = music_produce.produce(
            slug, n=1,
            genre_theme=theme["genre"], base_style=theme["style_prompt"],
            style_prompt=theme["style_prompt"], track_type="vocal",
            lyric_tone=theme["lyric_tone"], minutes=3.5,
            progress=lambda m: _step("음원·가사"),
        )
        mix = result.get("mix")
        if not mix or not mix.get("mp3_url"):
            raise RuntimeError("믹스 생성 실패(음원 없음).")

        _step("렌더")
        viz_spec = music_viz_analyzer.analyze_song(theme, mix)
        import tempfile
        work = Path(tempfile.mkdtemp(prefix="fulltest_"))
        bg = music_test._dummy_bg(work)  # 더미 배경(OPENAI 불필요) — 핵심은 진짜 음원
        video = music_video.make_video(
            theme, mix, background_path=str(bg), viz_spec=viz_spec, persist=False,
        )

        job["video_url"] = video.get("video_url")
        job["status"] = "done"
        _step("완료")
        logger.info("[music-fulltest] 완료 job=%s url=%s", job_id, job["video_url"])
    except Exception as e:  # noqa: BLE001 - 실패 원인 폴링으로 전달
        job["status"] = "error"
        job["error"] = str(e)[:300]
        logger.warning("[music-fulltest] 실패 job=%s: %s", job_id, e)
    finally:
        if work is not None:
            import shutil
            shutil.rmtree(work, ignore_errors=True)
        with _LOCK:
            if _active_job == job_id:
                _active_job = None
