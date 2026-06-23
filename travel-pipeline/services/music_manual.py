"""수동 영상 생성(#26) — 즉석 주제 1개 → 진짜 음원 1곡 → 가사·viz_spec → 풀 렌더 → 검토 큐.

대표가 버튼으로 수동 실행한 1곡을 **검토 큐에 정식 영상(status=pending)으로 적재**한다
(#25 풀 테스트의 persist=False 폐기 → persist=True). 일반 cron 제작과 동일한 파이프라인
(music_produce.produce: 가사 GPT → suno 보컬 → 마스터 → 믹스)을 1곡으로 돌리고, make_video
가 gpt-image 배경 + Remotion 풀 렌더 + record_pending(큐 저장)까지 수행한다. 유튜브 업로드는
하지 않는다(대표가 큐에서 썸네일 업로드 후 공개).

수 분~수십 분 걸리므로 BackgroundTasks 로 비동기 실행 + 인메모리 job 상태 폴링. 동시 1개 제한.
JobManager 는 인메모리(재시작 시 소실).
"""

from __future__ import annotations

import logging
import threading
import time
import uuid

logger = logging.getLogger(__name__)

# mood → 제작용 주제(스타일·톤 포함). genre/situation/mood 는 music_test 와 일관.
_THEMES: dict[str, dict] = {
    "citypop": {
        "genre": "시티팝", "situation": "출근 드라이브", "mood": "상쾌한",
        "title_kr": "시티팝 드라이브",
        "style_prompt": "city pop, 80s Japanese citypop, warm analog, lush chords, nostalgic",
        "lyric_tone": "상쾌하고 자유로운 아침 드라이브",
    },
    "cafe": {
        "genre": "재즈", "situation": "카페", "mood": "잔잔한",
        "title_kr": "카페 재즈",
        "style_prompt": "smooth jazz, cafe lounge, mellow piano, relaxed, warm",
        "lyric_tone": "잔잔하고 따뜻한 오후의 커피",
    },
    "ballad": {
        "genre": "발라드", "situation": "이별", "mood": "쓸쓸한",
        "title_kr": "이별 발라드",
        "style_prompt": "korean ballad, emotional piano, sad strings, tender",
        "lyric_tone": "쓸쓸한 이별의 밤",
    },
    "workout": {
        "genre": "EDM", "situation": "운동", "mood": "동기부여",
        "title_kr": "운동 EDM",
        "style_prompt": "energetic EDM, motivational, driving beat, uplifting",
        "lyric_tone": "힘차고 동기부여되는",
    },
    "sleep": {
        "genre": "Lo-fi", "situation": "수면 공부", "mood": "차분한",
        "title_kr": "수면 Lo-fi",
        "style_prompt": "lofi chill, calm, soft piano, ambient, sleepy",
        "lyric_tone": "나른하고 평온한 밤",
    },
}
_DEFAULT_MOOD = "citypop"

# 진행 단계(프론트 표시용 한국어): 주제 → 음원 → 가사 → 렌더 → 완료.
# 인메모리 job 저장소 + 동시 1개 제한 락.
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
_active_job: str | None = None


def available_moods() -> list[str]:
    return list(_THEMES.keys())


def _build_theme(mood: str) -> dict:
    preset = _THEMES.get(mood, _THEMES[_DEFAULT_MOOD])
    return {
        "slug": f"manual_{uuid.uuid4().hex[:12]}",
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
    """수동 영상 생성 1개 시작(동시 1개 제한). {ok, job_id} 또는 {ok:False, error, busy_job}."""
    global _active_job
    key = (mood or _DEFAULT_MOOD).strip().lower()
    with _LOCK:
        if _active_job and _JOBS.get(_active_job, {}).get("status") == "running":
            return {"ok": False, "error": "이미 영상 생성이 진행 중입니다. 완료 후 다시 시도하세요.", "busy_job": _active_job}
        job_id = uuid.uuid4().hex
        _JOBS[job_id] = {
            "job_id": job_id, "status": "running", "step": "주제",
            "mood": key, "video_url": None, "mix_id": None, "error": None,
            "created_at": time.time(),
        }
        _active_job = job_id
    # #36 운영 가시성 — DB 작업 추적(인메모리와 같은 job_id). best-effort.
    try:
        from services import music_jobs
        music_jobs.start_job("manual_render", job_id=job_id, metadata={"mood": key})
    except Exception as e:  # noqa: BLE001
        logger.debug("[music-manual] job 추적 시작 실패(무시): %s", e)
    return {"ok": True, "job_id": job_id}


def get_status(job_id: str) -> dict | None:
    job = _JOBS.get(job_id)
    if not job:
        return None
    return {k: job[k] for k in ("job_id", "status", "step", "mood", "video_url", "mix_id", "error")}


def run(job_id: str) -> None:
    """백그라운드 실행체 — produce(1곡) → make_video(persist=True) → 검토 큐 적재."""
    global _active_job
    job = _JOBS.get(job_id)
    if not job:
        return

    from services import music_jobs

    # 한국어 표시 단계 → 표준 단계(music_jobs.STEPS) 매핑(파이프라인 시각화용).
    _CANON = {"주제": "theme", "음원": "vocal", "가사": "lyrics", "음원·믹스": "mix", "렌더": "video"}

    def _step(name: str) -> None:
        job["step"] = name
        logger.info("[music-manual] job=%s step=%s", job_id, name)
        canon = _CANON.get(name)
        if canon:
            try:
                music_jobs.update_job_step(job_id, canon)
            except Exception:  # noqa: BLE001 - 추적 실패는 무시
                pass

    def _produce_progress(msg: str) -> None:
        if "가사" in msg:
            _step("가사")
        elif "마스터" in msg or "믹스" in msg:
            _step("음원·믹스")
        else:
            _step("음원")

    try:
        from services import music_produce, music_video, music_viz_analyzer

        theme = _build_theme(job["mood"])
        slug = theme["slug"]

        _step("음원")
        # 실제 제작: 가사(GPT) → suno 보컬 1곡 → 마스터 → 믹스(3~4분). 일반 cron 과 동일.
        result = music_produce.produce(
            slug, n=1,
            genre_theme=theme["genre"], base_style=theme["style_prompt"],
            style_prompt=theme["style_prompt"], track_type="vocal",
            lyric_tone=theme["lyric_tone"], minutes=3.5,
            progress=_produce_progress,
        )
        mix = result.get("mix")
        if not mix or not mix.get("mp3_url"):
            raise RuntimeError("믹스 생성 실패(음원 없음).")

        _step("렌더")
        viz_spec = music_viz_analyzer.analyze_song(theme, mix)
        # 일반 cron 과 동일: gpt-image 배경 + Remotion 풀 렌더 + record_pending(검토 큐 적재).
        video = music_video.make_video(theme, mix, viz_spec=viz_spec, persist=True)

        job["video_url"] = video.get("video_url")
        job["mix_id"] = video.get("video_id")
        job["status"] = "done"
        _step("완료")
        try:
            music_jobs.complete_job(job_id, mix_id=job["mix_id"])
        except Exception:  # noqa: BLE001
            pass
        logger.info("[music-manual] 완료 job=%s mix_id=%s url=%s", job_id, job["mix_id"], job["video_url"])
    except Exception as e:  # noqa: BLE001 - 실패 원인 폴링으로 전달
        job["status"] = "error"
        job["error"] = str(e)[:300]
        try:
            music_jobs.fail_job(job_id, str(e))
        except Exception:  # noqa: BLE001
            pass
        logger.warning("[music-manual] 실패 job=%s: %s", job_id, e)
    finally:
        with _LOCK:
            if _active_job == job_id:
                _active_job = None
