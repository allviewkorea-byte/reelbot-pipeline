"""수동 재렌더(#33 A) — 대표가 올린 깨끗한 이미지로 영상을 다시 렌더(검수 정확성).

검수 원칙: '본 것 = 유튜브에 올라갈 것' 100% 일치. CSS 오버레이 미리보기 대신 실제
Remotion 풀 렌더로 mp4 를 갱신한다. make_video(background_path=썸네일, persist=True)가
record_pending upsert 로 mp4_url 을 갱신하므로 별도 DB 갱신 불필요.

수 분 걸려 BackgroundTasks + 인메모리 job 폴링. mix_id 별 동시 1개 제한.
"""

from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
_active: dict[str, str] = {}  # mix_id → 진행 중 job_id


def start(mix_id: str, *, channel: str | None = None) -> dict:
    """재렌더 시작. {ok, job_id} 또는 {ok:False, error}. channel=None → where 채널."""
    with _LOCK:
        cur = _active.get(mix_id)
        if cur and _JOBS.get(cur, {}).get("status") == "running":
            return {"ok": False, "error": "이미 이 영상의 재렌더가 진행 중입니다."}
        job_id = uuid.uuid4().hex
        _JOBS[job_id] = {
            "job_id": job_id, "mix_id": mix_id, "status": "running",
            "step": "준비", "video_url": None, "error": None, "created_at": time.time(),
        }
        _active[mix_id] = job_id
    # #36 운영 가시성 — DB 작업 추적(인메모리와 같은 job_id). best-effort.
    try:
        from services import music_jobs
        music_jobs.start_job("rerender", job_id=job_id, mix_id=mix_id, channel=channel)
    except Exception as e:  # noqa: BLE001
        logger.debug("[music-rerender] job 추적 시작 실패(무시): %s", e)
    return {"ok": True, "job_id": job_id}


def get_status(job_id: str) -> dict | None:
    job = _JOBS.get(job_id)
    if not job:
        return None
    st = {k: job[k] for k in ("job_id", "mix_id", "status", "step", "video_url", "error")}
    if "thumbnail_url" in job:  # AI 이미지 생성 잡만(운동 채널) — 일반 재렌더 응답은 무변경
        st["thumbnail_url"] = job["thumbnail_url"]
    return st


def _load_mix(slug: str, mix_id: str) -> dict:
    from adapters import r2_storage
    mix = {"mix_id": mix_id, "tracks": [], "mp3_url": r2_storage.music_mix_url(slug, mix_id, "mp3")}
    try:
        tmp = Path(tempfile.gettempdir()) / f"{slug}_{mix_id}_rr.json"
        r2_storage.download_music_object(r2_storage.music_mix_key(slug, mix_id, "json"), str(tmp))
        meta = json.loads(tmp.read_text(encoding="utf-8"))
        mix["tracks"] = meta.get("tracks") or []
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-rerender] 믹스 JSON 로드 실패: %s", e)
    return mix


def run(job_id: str) -> None:
    """백그라운드: 썸네일 다운로드 → make_video(background_path, persist=True) → mp4_url 갱신."""
    job = _JOBS.get(job_id)
    if not job:
        return
    mix_id = job["mix_id"]

    from services import music_jobs

    # 재렌더 단계는 모두 영상 렌더 범주 → 표준 단계 'video' 로 표시.
    def _step(s: str) -> None:
        job["step"] = s
        logger.info("[music-rerender] job=%s step=%s", job_id, s)
        try:
            music_jobs.update_job_step(job_id, "video")
        except Exception:  # noqa: BLE001
            pass

    tmpdir: Path | None = None
    try:
        from adapters import r2_storage
        from services import music_theme, music_uploads, music_video

        row = music_uploads.get_upload(mix_id)
        if not row:
            raise RuntimeError("큐 항목을 찾을 수 없습니다.")
        if not row.get("thumbnail_r2_key"):
            raise RuntimeError("업로드된 이미지가 없습니다(이미지를 먼저 올리세요).")
        slug = row.get("slug") or ""
        theme = music_theme.get_theme(slug) or {
            "slug": slug, "title_kr": row.get("title_kr"),
            "genre": row.get("genre"), "mood": row.get("mood"),
            # 재렌더는 localizations 를 지우고 다시 만든다 — 여기서 빠지면 해시태그·
            # Copyright 가 다시 where 기준으로 굳는다(4단계).
            "tag_combo": row.get("tag_combo"), "channel": row.get("channel"),
        }
        mix = _load_mix(slug, mix_id)

        _step("이미지 준비")
        tmpdir = Path(tempfile.mkdtemp(prefix="rr_"))
        thumb = tmpdir / "thumb.png"
        r2_storage.download_music_object(row["thumbnail_r2_key"], str(thumb))

        # #50 인물(투명 PNG) — 있으면 다운로드해 최상단 레이어로. 없으면 None(기존 동작).
        char_path: str | None = None
        char_key = row.get("character_r2_key")
        if char_key:
            try:
                cpath = tmpdir / "character.png"
                r2_storage.download_music_object(char_key, str(cpath))
                char_path = str(cpath)
            except Exception as e:  # noqa: BLE001 - 인물 다운로드 실패해도 배경만으로 렌더 진행
                logger.warning("[music-rerender] 인물 다운로드 실패(배경만 렌더): %s", e)

        _step("렌더")
        # #39 영상별 PLAY LIST 표시(미지정/없음 → True). 싱글곡 OFF, 플레이리스트 ON.
        sp = row.get("show_playlist")
        show_playlist = True if sp is None else bool(sp)
        vres = music_video.make_video(
            theme, mix, background_path=str(thumb), character_path=char_path,
            persist=True, show_playlist=show_playlist,
        )
        # 운동 채널만 — publish 가 재렌더를 건너뛸 수 있게 렌더 정합 표식을 남긴다(PR-1).
        # where 는 표식을 남기지 않는다(= publish 는 지금처럼 항상 재렌더).
        from services.music_workout_style import is_workout_channel
        if is_workout_channel(row.get("channel")):
            from services import music_auto_image
            music_auto_image.record_render(
                slug, mix_id, bg_path=str(thumb), char_path=char_path, char_key=char_key,
                show_playlist=show_playlist, vres=vres, channel=row.get("channel"),
            )
        job["video_url"] = vres.get("video_url")
        job["status"] = "done"
        _step("완료")
        try:
            music_jobs.complete_job(job_id, mix_id=mix_id)
        except Exception:  # noqa: BLE001
            pass
        logger.info("[music-rerender] 완료 job=%s url=%s", job_id, job["video_url"])
    except Exception as e:  # noqa: BLE001
        job["status"] = "error"
        job["error"] = str(e)[:300]
        try:
            music_jobs.fail_job(job_id, str(e))
        except Exception:  # noqa: BLE001
            pass
        logger.warning("[music-rerender] 실패 job=%s: %s", job_id, e)
    finally:
        if tmpdir is not None:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
        with _LOCK:
            if _active.get(mix_id) == job_id:
                _active.pop(mix_id, None)


def run_with_ai_image(job_id: str) -> None:
    """운동 채널 검토대기 카드 [AI 이미지 생성] — 생성·검수 → 합격 시 이미지 교체 → run() 재렌더.

    불합격(재생성 1회 포함)이면 기존 이미지·영상은 그대로 두고 job 을 실패로 끝낸다(사유 포함).
    합격하면 대표가 "깨끗한 이미지 업로드"를 누른 것과 **같은 자리**(R2 + thumbnail_r2_key)에
    이미지를 놓고, 같은 재렌더(run)를 탄다. start() 로 만든 job 을 그대로 쓴다(폴링 경로 공유).
    """
    job = _JOBS.get(job_id)
    if not job:
        return
    mix_id = job["mix_id"]

    from services import music_jobs

    tmpdir: Path | None = None
    try:
        from adapters import r2_storage
        from services import music_auto_image, music_uploads

        row = music_uploads.get_upload(mix_id)
        if not row:
            raise RuntimeError("큐 항목을 찾을 수 없습니다.")
        slug = row.get("slug") or ""
        if not slug:
            raise RuntimeError("slug 를 확인할 수 없습니다.")
        if not r2_storage.is_available():
            raise RuntimeError("R2 미설정 — 이미지 저장 불가")

        job["step"] = "AI 이미지 생성"
        logger.info("[music-rerender] job=%s step=AI 이미지 생성", job_id)
        try:
            music_jobs.update_job_step(job_id, "video")
        except Exception:  # noqa: BLE001
            pass
        tmpdir = Path(tempfile.mkdtemp(prefix="aiimg_"))
        bg_path, summary = music_auto_image.prepare_for_render(
            job_id, (row.get("tag_combo") or {}).get("action"), str(tmpdir), reuse=False,
        )
        if not bg_path:
            raise RuntimeError(f"AI 이미지 검수 불합격 — 기존 상태 유지. {summary.get('summary', '')}"[:300])

        r2_storage.upload_music_thumbnail(bg_path, slug, mix_id)
        res = music_uploads.set_thumbnail(mix_id, r2_storage.music_thumbnail_key(slug, mix_id))
        if res.get("error"):
            raise RuntimeError(f"이미지 저장 실패: {res['error']}")
        # 수동 [재렌더] 라우트와 동일 — 다국어 캐시를 비워 새 렌더 기준으로 다시 만들게.
        try:
            music_uploads.clear_localizations(mix_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("[music-rerender] localizations 초기화 실패(계속): %s", e)
        job["thumbnail_url"] = f"{r2_storage.music_thumbnail_url(slug, mix_id)}?v={int(time.time())}"
    except Exception as e:  # noqa: BLE001
        job["status"] = "error"
        job["error"] = str(e)[:300]
        try:
            music_jobs.fail_job(job_id, str(e))
        except Exception:  # noqa: BLE001
            pass
        logger.warning("[music-rerender] AI 이미지 실패 job=%s: %s", job_id, e)
        with _LOCK:
            if _active.get(mix_id) == job_id:
                _active.pop(mix_id, None)
        return
    finally:
        if tmpdir is not None:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    run(job_id)
