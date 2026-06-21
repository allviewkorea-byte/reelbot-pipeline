"""음악 트랙(Rooftop Music) 메타 영구 저장소.

sunoapi.org 로 생성·R2 보관한 곡의 메타데이터를 Supabase `music_tracks` 테이블에
기록한다. Supabase 파이썬 SDK 없이 PostgREST(REST) 를 httpx 로 직접 호출한다
(신규 의존성 없음 — youtube_tokens.py 와 동일 패턴).

환경변수(프론트 lib/supabase 와 동일 네이밍):
  SUPABASE_URL          — 프로젝트 URL
  SUPABASE_SECRET_KEY   — service role(secret) 키 (대안: SUPABASE_SERVICE_ROLE_KEY / SUPABASE_KEY)

⚠️ 테이블은 GRANT 가 필요하다(레포에 마이그레이션 파일이 없어 Supabase SQL 에디터에서
수동 실행). docs/music_tracks.sql 참고:
  create table if not exists music_tracks (
    id text primary key,            -- audio_id (곡 단위 고유)
    theme_slug text not null,
    task_id text,
    audio_id text,
    title text,
    tags text,
    duration numeric,
    r2_key text,
    status text,
    created_at timestamptz default now()
  );
  grant all on table music_tracks to service_role, anon, authenticated;
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_TABLE = "music_tracks"


def _supabase_cfg() -> tuple[str | None, str | None]:
    url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    key = (
        os.getenv("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or ""
    ).strip()
    return (url or None, key or None)


def _http_err(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        return f"HTTP {e.response.status_code}: {e.response.text[:300]}"
    return f"{type(e).__name__}: {e}"


def is_available() -> bool:
    url, key = _supabase_cfg()
    return bool(url and key)


def upsert_track(record: dict) -> dict:
    """곡 메타 1행을 upsert(id 충돌 시 병합). 결과 dict 반환.

    record: {id, theme_slug, task_id, audio_id, title, tags, duration, r2_key, status}
    id(=audio_id) 로 멱등 — 폴링/콜백 양쪽이 같은 곡을 기록해도 1행만 남는다.
    Returns: {stored: bool, error: str|None}
    """
    url, key = _supabase_cfg()
    if not (url and key):
        logger.warning("[music-db] SUPABASE_URL / SUPABASE_SECRET_KEY 미설정 — DB 기록 생략")
        return {"stored": False, "error": "supabase 미설정"}
    try:
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",  # upsert
        }
        with httpx.Client(timeout=30.0) as c:
            r = c.post(
                f"{url}/rest/v1/{_TABLE}?on_conflict=id",
                headers=headers,
                json=[record],
            )
            r.raise_for_status()
        logger.info("[music-db] 저장 OK (id=%s)", record.get("id"))
        return {"stored": True, "error": None}
    except Exception as e:  # noqa: BLE001
        msg = _http_err(e)
        logger.warning("[music-db] 저장 실패(id=%s): %s", record.get("id"), msg)
        return {"stored": False, "error": msg}


def list_tracks(theme_slug: str, *, status: str | None = "SUCCESS") -> list[dict]:
    """테마의 곡 목록을 created_at 오름차순으로 조회(믹스 입력용).

    status 를 주면 해당 상태만(기본 SUCCESS). Supabase 미설정/오류 시 빈 리스트.
    """
    url, key = _supabase_cfg()
    if not (url and key):
        logger.warning("[music-db] SUPABASE 미설정 — 곡 조회 생략")
        return []
    try:
        headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        params = {
            "theme_slug": f"eq.{theme_slug}",
            "select": "id,theme_slug,task_id,audio_id,title,tags,duration,r2_key,status,created_at",
            "order": "created_at.asc",
        }
        if status:
            params["status"] = f"eq.{status}"
        with httpx.Client(timeout=30.0) as c:
            r = c.get(f"{url}/rest/v1/{_TABLE}", headers=headers, params=params)
            r.raise_for_status()
            rows = r.json()
        return rows if isinstance(rows, list) else []
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-db] 곡 조회 실패(theme=%s): %s", theme_slug, _http_err(e))
        return []
