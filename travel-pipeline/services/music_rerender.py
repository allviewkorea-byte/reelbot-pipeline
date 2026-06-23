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


def start(mix_id: str) -> dict:
    """재렌더 시작. {ok, job_id} 또는 {ok:False, error}."""
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
    return {"ok": True, "job_id": job_id}


def get_status(job_id: str) -> dict | None:
    job = _JOBS.get(job_id)
    if not job:
        return None
    return {k: job[k] for k in ("job_id", "mix_id", "status", "step", "video_url", "error")}


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

    def _step(s: str) -> None:
        job["step"] = s
        logger.info("[music-rerender] job=%s step=%s", job_id, s)

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
        }
        mix = _load_mix(slug, mix_id)

        _step("이미지 준비")
        tmpdir = Path(tempfile.mkdtemp(prefix="rr_"))
        thumb = tmpdir / "thumb.png"
        r2_storage.download_music_object(row["thumbnail_r2_key"], str(thumb))

        _step("렌더")
        vres = music_video.make_video(theme, mix, background_path=str(thumb), persist=True)
        job["video_url"] = vres.get("video_url")
        job["status"] = "done"
        _step("완료")
        logger.info("[music-rerender] 완료 job=%s url=%s", job_id, job["video_url"])
    except Exception as e:  # noqa: BLE001
        job["status"] = "error"
        job["error"] = str(e)[:300]
        logger.warning("[music-rerender] 실패 job=%s: %s", job_id, e)
    finally:
        if tmpdir is not None:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
        with _LOCK:
            if _active.get(mix_id) == job_id:
                _active.pop(mix_id, None)
