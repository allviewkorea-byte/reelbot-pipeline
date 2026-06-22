"""음악 유튜브 업로드 기록 저장소 (Supabase music_uploads).

업로드 성공 시 {slug, mix_id, youtube_video_id, youtube_url} 을 기록한다.
music_store 의 PostgREST(httpx) 패턴을 재사용(신규 의존성 0).

⚠️ music_uploads 테이블은 GRANT 필요(docs/music_uploads.sql, 수동 실행).
"""

from __future__ import annotations

import logging

import httpx

from services.music_store import _http_err, _supabase_cfg

logger = logging.getLogger(__name__)

_TABLE = "music_uploads"


def record_upload(slug: str, mix_id: str, youtube_video_id: str, youtube_url: str) -> dict:
    """업로드 1건 기록(insert). Supabase 미설정/실패해도 업로드 자체는 성공으로 둔다.

    Returns: {stored: bool, error: str|None}
    """
    url, key = _supabase_cfg()
    if not (url and key):
        logger.warning("[music-uploads] SUPABASE 미설정 — 업로드 기록 생략")
        return {"stored": False, "error": "supabase 미설정"}
    record = {
        "slug": slug,
        "mix_id": mix_id,
        "youtube_video_id": youtube_video_id,
        "youtube_url": youtube_url,
    }
    try:
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=30.0) as c:
            r = c.post(f"{url}/rest/v1/{_TABLE}", headers=headers, json=[record])
            r.raise_for_status()
        logger.info("[music-uploads] 기록 OK (video_id=%s)", youtube_video_id)
        return {"stored": True, "error": None}
    except Exception as e:  # noqa: BLE001
        msg = _http_err(e)
        logger.warning("[music-uploads] 기록 실패(video_id=%s): %s", youtube_video_id, msg)
        return {"stored": False, "error": msg}
