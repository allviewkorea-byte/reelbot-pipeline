"""유튜브 OAuth + 연동 상태 라우트 (prefix: /api/youtube).

- GET /api/youtube/auth     : 구글 OAuth 동의 화면으로 리다이렉트(첫 1회 로그인)
- GET /api/youtube/callback : 인증 코드 → refresh_token 저장 후 프론트로 리다이렉트
- GET /api/youtube/status   : 연동 여부(프론트 '연동됨 ✅' 표시용)

redirect_uri 가 /api/youtube/callback 이므로 이 라우터는 /api/youtube 에 마운트한다.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse

from services.youtube_oauth import (
    build_auth_url,
    exchange_code,
    is_connected,
    redirect_uri,
)
from services.youtube_tokens import _supabase_cfg

logger = logging.getLogger(__name__)

router = APIRouter()


def _frontend_settings_url(connected: bool) -> str:
    """콜백 후 돌아갈 프론트 설정 페이지 URL."""
    base = (
        os.getenv("FRONTEND_BASE_URL")
        or os.getenv("NEXT_PUBLIC_APP_URL")
        or "https://reelbot-pipeline.vercel.app"
    ).rstrip("/")
    flag = "connected" if connected else "error"
    return f"{base}/settings?youtube={flag}"


@router.get("/auth")
def auth():
    """구글 OAuth 동의 화면으로 리다이렉트한다."""
    try:
        return RedirectResponse(build_auth_url())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"OAuth URL 생성 실패: {e}") from e


@router.get("/callback")
def callback(code: str | None = None, error: str | None = None):
    """구글 콜백: 코드→토큰 교환→저장. 저장 실패 시 에러를 JSON 으로 그대로 노출(디버그)."""
    code_preview = (code[:8] + "…") if code else None
    logger.info(
        "[yt-callback] 진입: code_present=%s code_preview=%s error=%s redirect_uri=%s",
        bool(code), code_preview, error, redirect_uri(),
    )
    if error:
        logger.warning("[yt-callback] 구글 OAuth 오류 파라미터: %s", error)
        return JSONResponse(
            status_code=400,
            content={"ok": False, "step": "google_oauth", "error": error,
                     "redirect_uri": redirect_uri()},
        )
    if not code:
        raise HTTPException(status_code=400, detail="code 파라미터가 없습니다.")

    try:
        result = exchange_code(code)
    except Exception as e:  # noqa: BLE001
        logger.exception("[yt-callback] 토큰 교환 예외")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "step": "exchange_code", "error": repr(e),
                     "redirect_uri": redirect_uri()},
        )

    # 1) refresh_token 자체를 못 받은 경우
    if not result.get("refresh_token"):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "step": "no_refresh_token",
                     "error": result.get("error"),
                     "has_access_token": result.get("has_access_token"),
                     "redirect_uri": result.get("redirect_uri")},
        )

    save = result.get("save") or {}
    # 2) Supabase·로컬 둘 다 실패(영구/임시 저장 모두 안 됨)
    if not save.get("stored"):
        return JSONResponse(
            status_code=500,
            content={"ok": False, "step": "save",
                     "supabase_error": save.get("supabase_error"),
                     "local_error": save.get("local_error"),
                     "local_path": save.get("local_path"),
                     "channel_id": result.get("channel_id"),
                     "redirect_uri": result.get("redirect_uri")},
        )
    # 3) Supabase 는 실패했지만 로컬 폴백은 성공 — 에러를 응답에 노출(요청사항)
    if save.get("supabase_error"):
        return JSONResponse(
            status_code=200,
            content={"ok": True, "step": "saved_local_fallback",
                     "warning": "Supabase 저장 실패 — 로컬(/tmp) 폴백 사용(휘발성)",
                     "backend": save.get("backend"),
                     "supabase_error": save.get("supabase_error"),
                     "local_path": save.get("local_path"),
                     "channel_id": result.get("channel_id"),
                     "redirect_uri": result.get("redirect_uri")},
        )
    # 4) 완전 성공(Supabase 영구 저장) → 프론트로 리다이렉트
    logger.info("[yt-callback] 연동 완료(backend=%s)", save.get("backend"))
    return RedirectResponse(_frontend_settings_url(True))


@router.get("/status")
def status():
    """연동 여부 + 콜백 URL 재확인용 정보 반환."""
    url, key = _supabase_cfg()
    return {
        "connected": is_connected(),
        "channel_id": (os.getenv("YOUTUBE_CHANNEL_ID") or "").strip(),
        "auto_publish": (os.getenv("YOUTUBE_AUTO_PUBLISH") or "").strip().lower() == "true",
        "redirect_uri": redirect_uri(),
        "supabase_configured": bool(url and key),
    }
