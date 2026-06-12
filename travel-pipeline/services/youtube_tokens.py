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
# 로컬 폴백 경로(Railway 에서 쓰기 가능한 /tmp 기본). env 로 변경 가능.
_LOCAL = Path(os.getenv("YOUTUBE_TOKEN_LOCAL_PATH", "/tmp/youtube_token.json"))


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
    """httpx 에러를 사람이 읽을 수 있는 한 줄로(상태코드 + 본문 앞부분)."""
    if isinstance(e, httpx.HTTPStatusError):
        return f"HTTP {e.response.status_code}: {e.response.text[:300]}"
    return f"{type(e).__name__}: {e}"


def _load_local() -> dict:
    if _LOCAL.exists():
        try:
            return json.loads(_LOCAL.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_refresh_token(channel_id: str, refresh_token: str) -> dict:
    """refresh_token 을 영구 저장(Supabase 우선, 실패 시 로컬). 상세 결과 dict 반환.

    Returns: {stored, backend("supabase"|"local"|None), supabase_error, local_error, local_path}
    """
    result = {
        "stored": False,
        "backend": None,
        "supabase_error": None,
        "local_error": None,
        "local_path": str(_LOCAL),
    }
    if not refresh_token:
        result["supabase_error"] = "refresh_token 이 비어 있음"
        return result

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
            result.update(stored=True, backend="supabase")
            logger.info("[yt-token] Supabase 저장 OK (channel=%s)", channel_id)
            return result
        except Exception as e:  # noqa: BLE001
            msg = _http_err(e)
            result["supabase_error"] = msg
            logger.warning("[yt-token] Supabase 저장 실패 — 로컬 폴백 시도: %s", msg)
    else:
        result["supabase_error"] = "SUPABASE_URL / SUPABASE_SECRET_KEY 미설정"
        logger.warning("[yt-token] Supabase 미설정 — 로컬 폴백 시도")

    # 로컬 폴백
    try:
        _LOCAL.parent.mkdir(parents=True, exist_ok=True)
        data = _load_local()
        data[channel_id] = refresh_token
        _LOCAL.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        result.update(stored=True, backend="local")
        logger.warning("[yt-token] 로컬 저장 OK (%s) — ⚠️ 휘발성", _LOCAL)
    except Exception as e:  # noqa: BLE001
        result["local_error"] = f"{type(e).__name__}: {e}"
        logger.error("[yt-token] 로컬 저장도 실패: %s", result["local_error"])
    return result


def load_refresh_token(channel_id: str) -> str | None:
    """channel_id 의 refresh_token 조회(Supabase 우선, 실패/미설정 시 로컬 /tmp 폴백)."""
    url, key = _supabase_cfg()
    logger.warning(
        "[yt-token] load_refresh_token 시작: channel=%s supabase_configured=%s",
        channel_id, bool(url and key),
    )
    if url and key:
        try:
            headers = {"apikey": key, "Authorization": f"Bearer {key}"}
            with httpx.Client(timeout=30.0) as c:
                r = c.get(
                    f"{url}/rest/v1/{_TABLE}",
                    headers=headers,
                    params={"channel_id": f"eq.{channel_id}", "select": "refresh_token"},
                )
                logger.warning("[yt-token] Supabase 조회 응답: HTTP %s", r.status_code)
                r.raise_for_status()
                rows = r.json()
                logger.warning(
                    "[yt-token] Supabase rows=%d",
                    len(rows) if isinstance(rows, list) else -1,
                )
                if rows and rows[0].get("refresh_token"):
                    logger.warning(
                        "[yt-token] Supabase 에서 refresh_token 획득(channel=%s)", channel_id
                    )
                    return rows[0]["refresh_token"]
                # 정확 키 미스 → 채널 키 불일치 가능(저장 시 default vs 조회 시 실제 id 등).
                # 단일 채널 운영이므로 테이블의 아무 토큰으로 폴백한다.
                rany = c.get(
                    f"{url}/rest/v1/{_TABLE}",
                    headers=headers,
                    params={"select": "channel_id,refresh_token", "limit": "1"},
                )
                if rany.status_code == 200:
                    arows = rany.json()
                    if arows and arows[0].get("refresh_token"):
                        logger.warning(
                            "[yt-token] channel=%s 미스 → 저장된 토큰(channel=%s)으로 폴백",
                            channel_id, arows[0].get("channel_id"),
                        )
                        return arows[0]["refresh_token"]
                logger.warning(
                    "[yt-token] Supabase 에 토큰 없음(channel=%s) — 로컬 폴백 확인", channel_id
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("[yt-token] Supabase 조회 실패 — 로컬 폴백: %s", _http_err(e))
    else:
        logger.warning("[yt-token] Supabase 미설정 — 로컬(/tmp) 폴백 사용")

    data = _load_local()
    local = data.get(channel_id)
    if not local and data:
        # 로컬도 키 불일치 → 저장된 아무 토큰으로 폴백(단일 채널).
        k, local = next(iter(data.items()))
        logger.warning("[yt-token] 로컬 channel=%s 미스 → 저장된 키(%s)로 폴백", channel_id, k)
    logger.warning(
        "[yt-token] 최종 결과: %s (local path=%s)",
        "found" if local else "none", _LOCAL,
    )
    return local
