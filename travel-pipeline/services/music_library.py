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
import shutil
import tempfile
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
    *, genre: str | None = None, action: str | None = None, used: bool | None = None,
    limit: int = 100, offset: int = 0, channel: str | None = None,
) -> list[dict]:
    """적립곡 목록 + 재생 URL(play_url) 부착. 최신순. channel=None → where 채널."""
    rows = music_store.list_library(
        genre=genre, action=action, used=used, limit=limit, offset=offset, channel=channel
    )
    out: list[dict] = []
    for r in rows:
        out.append({
            "id": r.get("id"),
            "audio_id": r.get("audio_id"),
            "title": r.get("title") or "",
            "tags": r.get("tags") or "",
            "genre": r.get("genre") or "",
            "action": r.get("action") or "",
            "duration": r.get("duration"),
            "r2_key": r.get("r2_key") or "",
            "used": bool(r.get("used")),
            "channel": r.get("channel") or "",
            "created_at": r.get("created_at"),
            "play_url": r2_storage.music_object_url(r.get("r2_key") or ""),
        })
    return out


def stats(*, channel: str | None = None) -> list[dict]:
    """장르별 적립 현황 [{genre, total, unused}] (최다순). channel=None → where 채널."""
    return music_store.library_stats(channel=channel)


# ── 영상 만들기 (비동기 잡) ────────────────────────────────────────────
def get_status(job_id: str) -> dict | None:
    job = _JOBS.get(job_id)
    if not job:
        return None
    st = {k: job[k] for k in ("job_id", "status", "step", "video_url", "mix_id", "error")}
    if "image_review" in job:  # 운동 채널 AI 이미지 검수 결과(있을 때만 — where 응답 무변경)
        st["image_review"] = job["image_review"]
    return st


def cancel(job_id: str) -> dict:
    """진행 중 job 취소 요청. 현재 스텝 완료 후 큐 적재 없이 종료."""
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
    except Exception:  # noqa: BLE001
        pass
    logger.info("[music-library] 취소 요청 수신 job=%s", job_id)
    return {"ok": True}


def start(
    track_ids: list[str], mood: str | None = None, *,
    channel: str | None = None, auto_image: bool | None = None,
) -> dict:
    """선택곡 영상 제작 시작(동시 1개). {ok, job_id} 또는 {ok:False, error}.

    auto_image(PR-1): 운동 채널 배경 이미지 자동 생성. 운동 채널 기본 ON, where 는 항상 OFF.
    """
    global _active_job
    from services.music_auto_image import wants_auto_image
    auto = wants_auto_image(channel, auto_image)
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
            "video_url": None, "mix_id": None, "error": None, "cancelled": False,
            "created_at": time.time(),
            "channel": channel,  # run() 이 트랙 조회에 사용(None → where)
            "auto_image": auto,
        }
        _active_job = job_id
    try:
        from services import music_jobs
        music_jobs.start_job(
            "library_render", job_id=job_id,
            metadata={"track_ids": ids, "mood": mood}, channel=channel,
        )
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

    img_dir: str | None = None
    try:
        track_ids: list[str] = job["track_ids"]
        rows = music_store.get_tracks_by_ids(track_ids, channel=job.get("channel"))
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
            # 채널 축(4단계) — 해시태그·본문 Copyright 가 채널을 알게 한다. None → where.
            "channel": job.get("channel"),
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

        if job.get("cancelled"):
            logger.info("[music-library] 취소됨 job=%s", job_id)
            return

        # 운동 채널 — 렌더 전에 배경 이미지 생성·검수(PR-1). 실패면 None → 기존 블랙 배경 렌더.
        # 라이브러리 믹스엔 tag_combo 가 없어 첫 트랙의 action 으로 축을 고른다.
        bg_path: str | None = None
        if job.get("auto_image"):
            _step("이미지", "video")
            from services import music_auto_image
            img_dir = tempfile.mkdtemp(prefix="autoimg_")
            bg_path, job["image_review"] = music_auto_image.prepare_for_render(
                job_id, rows[0].get("action") or None, img_dir,
            )
            if job.get("cancelled"):
                logger.info("[music-library] 취소됨 job=%s", job_id)
                return

        # ③ 풀 렌더(분할 렌더·배경·자동 썸네일은 make_video 가 자동) → 검토 큐 적재.
        _step("렌더", "video")
        viz_spec = music_viz_analyzer.analyze_song(theme, mix)

        try:
            from services import music_meta
            built = music_meta.build_title(theme, viz_spec)
            if built:
                theme["title_kr"] = built
        except Exception as e:  # noqa: BLE001
            logger.warning("[music-library] build_title 실패(기본값 유지): %s", e)

        # 복구 A·B·C — 곡은 이미 있다(라이브러리). 렌더 실패(폴백·로컬 경로·로고 누락)면 같은 곡·주제로
        # 영상만 다시(최대 2회). Suno 호출 없음.
        from services import music_recovery
        rec = {"kind": "library", "slug": slug, "theme": music_recovery._theme_brief(theme),
               "channel": job.get("channel"), "auto_image": bool(job.get("auto_image")),
               "mix_id": mix.get("mix_id"), "minutes": 10.0, "stage": "rendering",
               "tracks": [{k: r.get(k) for k in ("audio_id", "r2_key", "duration", "title", "tags")} for r in rows]}
        music_jobs.merge_metadata(job_id, {"recovery": rec})
        with music_recovery.Heartbeat(job_id):
            try:
                if bg_path:
                    video = music_video.make_video(
                        theme, mix, viz_spec=viz_spec, persist=True, background_path=bg_path,
                    )
                else:
                    video = music_video.make_video(theme, mix, viz_spec=viz_spec, persist=True)
                chk = music_recovery.check_render(video, channel=job.get("channel"))
                if not chk["ok"]:
                    raise music_recovery.RenderFailed(chk["reason"], video)
                music_jobs.merge_metadata(job_id, {"render_check": chk})
            except Exception as e:  # noqa: BLE001
                if job.get("cancelled"):
                    raise
                logger.warning("[music-library] 영상 단계 실패 → 복구 시도 job=%s: %s", job_id, e)
                video, _chk = music_recovery.recover_video(
                    rec, job_id=job_id, first_error=e, bg_path=bg_path, step=lambda n: _step(n),
                )
        job["frame_thumb_key"] = video.get("frame_thumb_key")

        # ④ 사용된 트랙 used=true 마킹(best-effort).
        for r in rows:
            if not music_store.mark_track_used(r.get("audio_id")):
                logger.warning("[music-library] used 마킹 실패(id=%s) — 진행", r.get("audio_id"))

        job["video_url"] = video.get("video_url")
        job["mix_id"] = video.get("video_id")
        # 채널 보정 — record_pending 은 렌더 경로(music_video, 수정 금지)에서 불려 채널을
        # 못 받는다. 렌더를 시킨 이쪽이 mix_id 로 사후에 박는다. best-effort.
        if job.get("channel") and job.get("mix_id"):
            try:
                from services import music_uploads
                music_uploads.set_channel(job["mix_id"], job["channel"])
            except Exception as e:  # noqa: BLE001
                logger.warning("[music-library] 채널 보정 실패(무시): %s", e)
        # 이미지를 대표 업로드와 같은 자리(thumbnail_r2_key)에 연결 — 큐 행이 생긴 렌더 뒤에만 가능.
        if bg_path and job.get("mix_id"):
            from services import music_auto_image
            att = music_auto_image.attach_after_render(
                slug, job["mix_id"], bg_path, video, channel=job.get("channel"),
            )
            if att.get("error"):
                job["image_review"] = {**job.get("image_review", {}), "ok": False,
                                       "summary": f"이미지 연결 실패: {att['error'][:120]}"}
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
        if img_dir:
            shutil.rmtree(img_dir, ignore_errors=True)
        with _LOCK:
            if _active_job == job_id:
                _active_job = None
