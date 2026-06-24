"""음원 라이브러리(#48) — 적립곡(music_tracks) 큐레이션 + 선택곡으로 영상 제작.

대표가 라이브러리에서 직접 고른 트랙들로 **Suno 호출 없이** 곧장 영상을 만든다:
선택 트랙 → (마스터 멱등) → build_mix 크로스페이드 → make_video 풀 렌더 → 검토 큐(pending).
이미 만들어진 음원을 재사용하므로 크레딧 0 + 제작 시간 대폭 단축.

기존 수동/자동 경로(music_manual / run_theme)는 건드리지 않는다 — 이건 **새 경로**다.
수 분~수십 분 걸리므로 BackgroundTasks + 인메모리 job 폴링(동시 1개). music_manual 과
동일한 패턴(별도 JobManager — 두 경로의 락은 독립).
"""

from __future__ import annotations

import logging
import threading
import time
import uuid

from adapters import r2_storage
from services import music_genres, music_store

logger = logging.getLogger(__name__)

# 인메모리 job 저장소 + 동시 1개 제한 락(수동 경로와 독립).
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
_active_job: str | None = None

_TRACK_MIN, _TRACK_MAX = 1, 100


# ── 조회 (목록·통계) ───────────────────────────────────────────────────
def list_library(
    *, genre: str | None = None, used: bool | None = None, limit: int = 100, offset: int = 0,
) -> list[dict]:
    """적립곡 목록 + 재생 URL(play_url) 부착. 최신순."""
    rows = music_store.list_library(genre=genre, used=used, limit=limit, offset=offset)
    out: list[dict] = []
    for r in rows:
        out.append({
            "id": r.get("id"),
            "audio_id": r.get("audio_id"),
            "title": r.get("title") or "",
            "tags": r.get("tags") or "",
            "genre": r.get("genre") or "",
            "duration": r.get("duration"),
            "r2_key": r.get("r2_key") or "",
            "used": bool(r.get("used")),
            "created_at": r.get("created_at"),
            "play_url": r2_storage.music_object_url(r.get("r2_key") or ""),
        })
    return out


def stats() -> list[dict]:
    """장르별 적립 현황 [{genre, total, unused}] (최다순)."""
    return music_store.library_stats()


# ── 영상 만들기 (비동기 잡) ────────────────────────────────────────────
def get_status(job_id: str) -> dict | None:
    job = _JOBS.get(job_id)
    if not job:
        return None
    return {k: job[k] for k in ("job_id", "status", "step", "video_url", "mix_id", "error")}


def start(track_ids: list[str], mood: str | None = None) -> dict:
    """선택곡 영상 제작 시작(동시 1개). {ok, job_id} 또는 {ok:False, error}."""
    global _active_job
    ids = [str(t).strip() for t in (track_ids or []) if str(t).strip()]
    if not ids:
        return {"ok": False, "error": "선택된 곡이 없습니다."}
    if len(ids) > _TRACK_MAX:
        ids = ids[:_TRACK_MAX]
    with _LOCK:
        if _active_job and _JOBS.get(_active_job, {}).get("status") == "running":
            return {"ok": False, "error": "이미 영상 생성이 진행 중입니다. 완료 후 다시 시도하세요.", "busy_job": _active_job}
        job_id = uuid.uuid4().hex
        _JOBS[job_id] = {
            "job_id": job_id, "status": "running", "step": "준비",
            "track_ids": ids, "mood": (mood or "").strip().lower() or None,
            "video_url": None, "mix_id": None, "error": None, "created_at": time.time(),
        }
        _active_job = job_id
    try:
        from services import music_jobs
        music_jobs.start_job("library_render", job_id=job_id, metadata={"track_ids": ids, "mood": mood})
    except Exception as e:  # noqa: BLE001
        logger.debug("[music-library] job 추적 시작 실패(무시): %s", e)
    return {"ok": True, "job_id": job_id}


def run(job_id: str) -> None:
    """백그라운드 실행체 — 선택곡 → 마스터 → 믹스 → 렌더 → 검토 큐. Suno 호출 없음."""
    global _active_job
    job = _JOBS.get(job_id)
    if not job:
        return

    from services import music_jobs, music_master, music_mix, music_video, music_viz_analyzer

    def _step(name: str, canon: str | None = None) -> None:
        job["step"] = name
        logger.info("[music-library] job=%s step=%s", job_id, name)
        if canon:
            try:
                music_jobs.update_job_step(job_id, canon)
            except Exception:  # noqa: BLE001
                pass

    try:
        track_ids: list[str] = job["track_ids"]
        rows = music_store.get_tracks_by_ids(track_ids)
        # SUCCESS + r2_key 있는 것만 사용.
        rows = [r for r in rows if (r.get("status") == "SUCCESS") and r.get("r2_key") and r.get("audio_id")]
        if not rows:
            raise RuntimeError("유효한 트랙이 없습니다(이미 삭제됐거나 ID 오류).")

        # 장르/무드: 지정값 우선, 없으면 첫 트랙 장르.
        genre_id = music_genres.normalize_mood_key(job.get("mood") or (rows[0].get("genre") or ""))
        preset = music_genres.preset(genre_id)
        slug = f"library_{uuid.uuid4().hex[:12]}"
        theme = {
            "slug": slug,
            "title_kr": preset["title_kr"],
            "genre": preset["genre"],
            "situation": preset.get("situation", ""),
            "mood": preset["mood"],
            "type": "instrumental",  # 라이브러리 믹스는 가사 임베드 없음(자막 미동기).
        }

        # ① 마스터(멱등) — 원본 r2_key 소스로 새 slug 아래 마스터본 생성. Suno 호출 없음.
        _step("마스터", "mix")
        mastered = music_master.master_theme(slug, rows)
        if not mastered:
            raise RuntimeError("마스터링 실패(원본 음원 없음).")

        # ② 크로스페이드 믹스.
        _step("믹스", "mix")
        mix = music_mix.build_mix(slug, rows)
        if not mix or not mix.get("mp3_url"):
            raise RuntimeError("믹스 생성 실패.")

        # ③ 풀 렌더(분할 렌더·배경·자동 썸네일은 make_video 가 자동) → 검토 큐 적재.
        _step("렌더", "video")
        viz_spec = music_viz_analyzer.analyze_song(theme, mix)
        video = music_video.make_video(theme, mix, viz_spec=viz_spec, persist=True)

        # ④ 사용된 트랙 used=true 마킹(best-effort).
        for r in rows:
            if not music_store.mark_track_used(r.get("audio_id")):
                logger.warning("[music-library] used 마킹 실패(id=%s) — 진행", r.get("audio_id"))

        job["video_url"] = video.get("video_url")
        job["mix_id"] = video.get("video_id")
        job["status"] = "done"
        _step("완료")
        try:
            music_jobs.complete_job(job_id, mix_id=job["mix_id"])
        except Exception:  # noqa: BLE001
            pass
        logger.info("[music-library] 완료 job=%s mix_id=%s", job_id, job["mix_id"])
    except Exception as e:  # noqa: BLE001 - 실패 원인 폴링으로 전달
        job["status"] = "error"
        job["error"] = str(e)[:300]
        try:
            from services import music_jobs
            music_jobs.fail_job(job_id, str(e))
        except Exception:  # noqa: BLE001
            pass
        logger.warning("[music-library] 실패 job=%s: %s", job_id, e)
    finally:
        with _LOCK:
            if _active_job == job_id:
                _active_job = None
