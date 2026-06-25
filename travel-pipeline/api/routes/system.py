"""시스템 상태 API — 각 서비스 헬스체크 + 최근 에러 목록.

GET /api/system/status  → 서비스별 상태(읽기 전용, 변경 없음)
GET /api/system/errors   → 최근 실패 작업 목록(music_jobs 테이블)
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])

SUNO_BASE = "https://api.sunoapi.org/api/v1"
_SUNO_CREDIT_WARNING = 100
_SUNO_CREDIT_ERROR = 10


def _check_railway() -> dict:
    return {"status": "ok", "latency_ms": 0}


def _check_supabase() -> dict:
    from services.music_store import _supabase_cfg
    url, key = _supabase_cfg()
    if not url or not key:
        return {"status": "error", "message": "SUPABASE_URL/KEY 미설정"}
    try:
        t0 = time.monotonic()
        with httpx.Client(timeout=8.0) as c:
            r = c.get(
                f"{url}/rest/v1/",
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                },
                params={"select": "1", "limit": "1"},
            )
        ms = round((time.monotonic() - t0) * 1000)
        if r.status_code < 400:
            return {"status": "ok", "latency_ms": ms}
        return {"status": "error", "message": f"HTTP {r.status_code}", "latency_ms": ms}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "message": str(e)[:200]}


def _check_r2() -> dict:
    base = (
        os.getenv("R2_MUSIC_PUBLIC_BASE_URL")
        or os.getenv("R2_PUBLIC_BASE_URL")
        or ""
    ).strip().rstrip("/")
    if not base:
        return {"status": "error", "message": "R2 퍼블릭 URL 미설정"}
    try:
        t0 = time.monotonic()
        with httpx.Client(timeout=8.0) as c:
            r = c.head(base + "/")
        ms = round((time.monotonic() - t0) * 1000)
        if r.status_code < 500:
            return {"status": "ok", "latency_ms": ms}
        return {"status": "error", "message": f"HTTP {r.status_code}", "latency_ms": ms}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "message": str(e)[:200]}


def _check_aws_lambda() -> dict:
    fn = (os.getenv("REMOTION_LAMBDA_FUNCTION_NAME") or "").strip()
    serve = (os.getenv("REMOTION_SERVE_URL") or "").strip()
    if not fn:
        return {"status": "warn", "message": "REMOTION_LAMBDA_FUNCTION_NAME 미설정"}
    if not serve:
        return {"status": "warn", "message": "REMOTION_SERVE_URL 미설정"}
    return {"status": "ok", "function": fn}


def _check_suno() -> dict:
    key = (os.getenv("SUNOAPI_ORG_KEY") or "").strip()
    if not key:
        return {"status": "error", "message": "SUNOAPI_ORG_KEY 미설정"}
    try:
        t0 = time.monotonic()
        with httpx.Client(timeout=10.0) as c:
            # sunoapi.org 크레딧 조회: GET /api/v1/generate/credit
            # 응답 봉투 {code, msg, data} 에서 data 가 남은 크레딧(정수) 그대로.
            r = c.get(
                f"{SUNO_BASE}/generate/credit",
                headers={"Authorization": f"Bearer {key}"},
            )
        ms = round((time.monotonic() - t0) * 1000)
        if r.status_code >= 400:
            # 키 만료·엔드포인트 변경 등으로 조회만 실패해도 서비스 자체는 살아있을 수
            # 있으므로 error 가 아닌 warn 으로 처리(대시보드 빨간불 오인 방지).
            return {"status": "warn", "message": "크레딧 조회 불가", "latency_ms": ms}
        data = r.json().get("data")
        # data 가 정수면 그 자체가 크레딧, 객체면 totalCredits/credits 키에서 추출.
        credits = None
        if isinstance(data, (int, float)):
            credits = int(data)
        elif isinstance(data, dict):
            raw = data.get("totalCredits")
            if raw is None:
                raw = data.get("credits")
            if raw is not None:
                credits = int(raw)
        if credits is not None:
            if credits < _SUNO_CREDIT_ERROR:
                return {"status": "error", "message": "크레딧 부족", "credits": credits, "latency_ms": ms}
            if credits < _SUNO_CREDIT_WARNING:
                return {"status": "warn", "message": "크레딧 낮음", "credits": credits, "latency_ms": ms}
            return {"status": "ok", "credits": credits, "latency_ms": ms}
        return {"status": "ok", "latency_ms": ms}
    except Exception as e:  # noqa: BLE001
        logger.warning("[system] Suno 크레딧 조회 실패: %s", e)
        return {"status": "warn", "message": "크레딧 조회 불가"}


def _check_anthropic() -> dict:
    key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        return {"status": "error", "message": "ANTHROPIC_API_KEY 미설정"}
    return {"status": "ok"}


def _check_youtube() -> dict:
    try:
        from services.music_store import _supabase_cfg
        url, key = _supabase_cfg()
        if not url or not key:
            return {"status": "error", "message": "Supabase 미설정(토큰 조회 불가)"}
        with httpx.Client(timeout=8.0) as c:
            r = c.get(
                f"{url}/rest/v1/youtube_tokens",
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                },
                params={"select": "channel_id", "limit": "1"},
            )
        if r.status_code >= 400:
            return {"status": "error", "message": f"토큰 테이블 조회 HTTP {r.status_code}"}
        rows = r.json()
        if not rows:
            return {"status": "error", "message": "YouTube 토큰 없음"}
        ch = rows[0].get("channel_id", "")
        return {"status": "ok", "channel": ch}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "message": str(e)[:200]}


@router.get("/status")
def system_status():
    results = {
        "railway": _check_railway(),
        "supabase": _check_supabase(),
        "r2": _check_r2(),
        "aws_lambda": _check_aws_lambda(),
        "suno": _check_suno(),
        "anthropic": _check_anthropic(),
        "youtube": _check_youtube(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    return results


@router.get("/errors")
def system_errors(limit: int = 20):
    try:
        from services.music_store import _supabase_cfg
        url, key = _supabase_cfg()
        if not url or not key:
            return {"errors": [], "message": "Supabase 미설정"}
        with httpx.Client(timeout=10.0) as c:
            r = c.get(
                f"{url}/rest/v1/music_jobs",
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                },
                params={
                    "select": "job_id,job_type,step,error,created_at",
                    "status": "eq.failed",
                    "order": "created_at.desc",
                    "limit": str(min(limit, 50)),
                },
            )
        if r.status_code >= 400:
            return {"errors": [], "message": f"조회 실패 HTTP {r.status_code}"}
        rows = r.json()
        return {
            "errors": [
                {
                    "job_id": row.get("job_id", ""),
                    "type": row.get("job_type", ""),
                    "step": row.get("step", ""),
                    "error_message": (row.get("error") or "")[:300],
                    "created_at": row.get("created_at", ""),
                }
                for row in (rows if isinstance(rows, list) else [])
            ],
        }
    except Exception as e:  # noqa: BLE001
        return {"errors": [], "message": str(e)[:200]}
