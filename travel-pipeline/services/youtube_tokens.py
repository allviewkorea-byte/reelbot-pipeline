"""유튜브 OAuth refresh_token 영구 저장소.

OAuth 콜백에서 받은 refresh_token 을 Supabase `youtube_tokens` 테이블에 보관하고
(영구), 업로드 시 꺼내 access_token 을 갱신한다. Supabase 파이썬 클라이언트 없이
PostgREST(REST) 를 httpx 로 직접 호출한다(신규 의존성 없음).

환경변수(프론트 lib/supabase 와 동일 네이밍):
  SUPABASE_URL          — 프로젝트 URL
  SUPABASE_SECRET_KEY   — service role(secret) 키 (대안: SUPABASE_SERVICE_ROLE_KEY / SUPABASE_KEY)

Supabase 미설정 시 로컬 JSON 으로 폴백한다(⚠️ Railway 휘발성 — 영구 보관하려면
Supabase 설정 필요). 테이블 스키마(권장):
  create table youtube_tokens (
    channel_id text primary key,
    refresh_token text not null,
    updated_at timestamptz default now()
  );
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_TABLE = "youtube_tokens"
_LOCAL = Path("output/youtube_tokens.json")


def _supabase_cfg() -> tuple[str | None, str | None]:
    url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    key = (
        os.getenv("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or ""
    ).strip()
    return (url or None, key or None)


def _load_local() -> dict:
    if _LOCAL.exists():
        try:
            return json.loads(_LOCAL.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_refresh_token(channel_id: str, refresh_token: str) -> None:
    """refresh_token 을 channel_id 키로 영구 저장(Supabase 우선, 실패 시 로컬)."""
    if not refresh_token:
        return
    url, key = _supabase_cfg()
    if url and key:
        try:
            headers = {
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates",  # upsert
            }
            body = [{"channel_id": channel_id, "refresh_token": refresh_token}]
            with httpx.Client(timeout=30.0) as c:
                r = c.post(
                    f"{url}/rest/v1/{_TABLE}?on_conflict=channel_id",
                    headers=headers, json=body,
                )
                r.raise_for_status()
            logger.info("유튜브 refresh_token Supabase 저장 완료(channel=%s)", channel_id)
            return
        except Exception as e:  # noqa: BLE001
            logger.warning("Supabase 토큰 저장 실패 — 로컬 폴백: %s", e)
    _LOCAL.parent.mkdir(parents=True, exist_ok=True)
    data = _load_local()
    data[channel_id] = refresh_token
    _LOCAL.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    logger.warning(
        "유튜브 refresh_token 로컬 저장(휘발성). 영구 보관하려면 SUPABASE_URL/"
        "SUPABASE_SECRET_KEY 를 설정하세요."
    )


def load_refresh_token(channel_id: str) -> str | None:
    """channel_id 의 refresh_token 조회(Supabase 우선, 실패/미설정 시 로컬)."""
    url, key = _supabase_cfg()
    if url and key:
        try:
            headers = {"apikey": key, "Authorization": f"Bearer {key}"}
            with httpx.Client(timeout=30.0) as c:
                r = c.get(
                    f"{url}/rest/v1/{_TABLE}",
                    headers=headers,
                    params={"channel_id": f"eq.{channel_id}", "select": "refresh_token"},
                )
                r.raise_for_status()
                rows = r.json()
                if rows:
                    return rows[0].get("refresh_token")
        except Exception as e:  # noqa: BLE001
            logger.warning("Supabase 토큰 조회 실패 — 로컬 폴백: %s", e)
    return _load_local().get(channel_id)
