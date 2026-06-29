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

# 장르 체계 SSOT(#45) — 14장르 프리셋·기본값. music_genres 는 의존성 0(순환 안전).
from services import music_genres

logger = logging.getLogger(__name__)

_DEFAULT_MOOD = music_genres.DEFAULT_GENRE

# 진행 단계(프론트 표시용 한국어): 주제 → 음원 → 가사 → 렌더 → 완료.
# 인메모리 job 저장소 + 동시 1개 제한 락.
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
_active_job: str | None = None


def available_moods() -> list[str]:
    return list(music_genres.GENRE_IDS)


# #42 수동 생성 곡수 1~100(범위 밖 클램프). 미지정 → 1(기존 동작 = 회귀 0).
_TRACK_MIN, _TRACK_MAX = 1, 100


def _clamp_track_count(n) -> int:
    try:
        return max(_TRACK_MIN, min(_TRACK_MAX, int(n)))
    except (TypeError, ValueError):
        return 1


def _build_theme(mood: str, track_count: int = 1, tag_combo: dict | None = None) -> dict:
    if tag_combo:
        from services import music_tags
        has_chips = any(tag_combo.get(k) for k in ("genre", "situation", "emotion", "tempo", "format", "charm"))
        if not has_chips:
            tag_combo = music_tags.smart_random(tag_combo)
        style = music_tags.tags_to_suno_style(tag_combo)
        instrumental = music_tags.is_instrumental(tag_combo)
        action = tag_combo.get("action") or ""
        genres = tag_combo.get("genre") or []
        genre_label = ", ".join(genres[:2]) if genres else "custom"
        lyric_tone = ""
        if action == "sleep" and not instrumental:
            lyric_tone = "잔잔하고 차분한, 잠들기 좋은, 느린, 위로하는 톤. 신나거나 빠른 분위기 금지."
        elif action == "baby_sleep" and not instrumental:
            lyric_tone = "자장가 톤, 아기에게 들려주는 부드럽고 따뜻한 가사. 느리고 반복적인 리듬."
        elif action == "focus" and not instrumental:
            lyric_tone = "차분하고 집중에 방해되지 않는 톤. 가사는 최소한으로, 반복적이고 단순하게."
        return {
            "slug": f"manual_{uuid.uuid4().hex[:12]}",
            "title_kr": f"태그 조합 — {action}" if action else "태그 조합",
            "genre": genre_label,
            "situation": action,
            "mood": action or "custom",
            "type": "instrumental" if instrumental else "vocal",
            "style_prompt": style,
            "lyric_tone": lyric_tone,
            "track_count": _clamp_track_count(track_count),
            "tag_combo": tag_combo,
        }
    preset = music_genres.preset(mood)
    return {
        "slug": f"manual_{uuid.uuid4().hex[:12]}",
        "title_kr": preset["title_kr"],
        "genre": preset["genre"],
        "situation": preset["situation"],
        "mood": preset["mood"],
        "type": "vocal",
        "style_prompt": preset["style_prompt"],
        "lyric_tone": preset["lyric_tone"],
        "track_count": _clamp_track_count(track_count),
    }


def start(mood: str | None = None, track_count: int | None = None, tag_combo: dict | None = None) -> dict:
    """수동 영상 생성 1개 시작(동시 1개 제한). {ok, job_id} 또는 {ok:False, error, busy_job}.

    track_count(#42): 영상에 넣을 곡수 1~100(미지정→1). 곡수 = Suno 호출 수 = 영상 길이(#40).
    tag_combo(③-A): 8축 태그 조합. 있으면 mood 무시, 태그 기반 style 생성.
    """
    global _active_job
    key = music_genres.normalize_mood_key(mood or _DEFAULT_MOOD)
    tc = _clamp_track_count(track_count if track_count is not None else 1)
    with _LOCK:
        if _active_job and _JOBS.get(_active_job, {}).get("status") == "running":
            return {"ok": False, "error": "이미 영상 생성이 진행 중입니다. 완료 후 다시 시도하세요.", "busy_job": _active_job}
        job_id = uuid.uuid4().hex
        _JOBS[job_id] = {
            "job_id": job_id, "status": "running", "step": "주제",
            "mood": key, "track_count": tc, "video_url": None, "mix_id": None, "error": None,
            "cancelled": False,
            "created_at": time.time(),
            "tag_combo": tag_combo,
        }
        _active_job = job_id
    meta = {"mood": key, "track_count": tc}
    if tag_combo:
        meta["tag_combo"] = tag_combo
    try:
        from services import music_jobs
        music_jobs.start_job("manual_render", job_id=job_id, metadata=meta)
    except Exception as e:  # noqa: BLE001
        logger.debug("[music-manual] job 추적 시작 실패(무시): %s", e)
    return {"ok": True, "job_id": job_id}


def cancel(job_id: str) -> dict:
    """진행 중 job 취소 요청(#26-C). 현재 스텝(Suno·렌더)은 완료되나 큐 적재 없이 종료한다.

    백그라운드 스레드는 강제 종료 불가 → 협조적 취소: 플래그를 세우고 status='cancelled' 로 바꾼다.
    run() 이 렌더 직전 플래그를 보고 early return → record_pending 미실행 → 검토 큐에 안 쌓인다.
    """
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return {"ok": False, "error": "job 없음"}
        if job["status"] != "running":
            return {"ok": False, "error": f"취소 불가 상태: {job['status']}"}
        job["cancelled"] = True
        job["status"] = "cancelled"
    try:
        from services import music_jobs
        music_jobs.fail_job(job_id, "사용자 취소")
    except Exception:  # noqa: BLE001 - 추적 실패는 무시
        pass
    logger.info("[music-manual] 취소 요청 수신 job=%s", job_id)
    return {"ok": True}


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

        tc = _clamp_track_count(job.get("track_count", 1))
        theme = _build_theme(job["mood"], tc, tag_combo=job.get("tag_combo"))
        slug = theme["slug"]

        _step("음원")
        # 실제 제작: 가사(GPT) → suno 보컬 N곡 → 마스터 → 믹스. 일반 cron 과 동일(#42 곡수 N).
        # #46: 수동 무드 키 = 14장르 id → 고정 태그·instrumental·재활용 적용.
        result = music_produce.produce(
            slug, n=tc,
            genre_theme=theme["genre"], base_style=theme["style_prompt"],
            style_prompt=theme["style_prompt"], track_type=theme.get("type", "vocal"),
            lyric_tone=theme["lyric_tone"], minutes=3.5,
            genre_id=None if job.get("tag_combo") else job["mood"],
            action=(job.get("tag_combo") or {}).get("action") or "",
            progress=_produce_progress,
        )
        mix = result.get("mix")
        if not mix or not mix.get("mp3_url"):
            raise RuntimeError("믹스 생성 실패(음원 없음).")

        # #26-C 취소 체크 — 음원 생성까지 끝났어도 렌더 시작 전 취소면 큐 적재 없이 종료.
        if job.get("cancelled"):
            logger.info("[music-manual] 취소됨 → 렌더 생략 job=%s", job_id)
            return

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
