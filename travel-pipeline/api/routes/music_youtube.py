"""음악 채널(Revezen) 유튜브 OAuth 라우트 (prefix: /api/music/youtube).

백곰 /api/youtube/* 와 완전 분리. 패턴은 동일하되 음악 OAuth(music_youtube_oauth)를 쓴다.
- GET /api/music/youtube/auth     : 구글 OAuth 동의 화면으로 리다이렉트
- GET /api/music/youtube/callback : 코드 → refresh_token(음악 채널 ID로) 저장
- GET /api/music/youtube/status   : 연동 여부

redirect_uri 는 env YOUTUBE_REDIRECT_URI_MUSIC 우선, 없으면 요청 기반(/api/music/youtube/callback)
으로 계산한다(auth·callback 이 동일하게 계산 → 일치).
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from services.music_youtube_oauth import (
    build_auth_url,
    exchange_code,
    is_connected,
    music_channel_id,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _redirect_uri(request: Request) -> str:
    """env YOUTUBE_REDIRECT_URI_MUSIC 우선, 없으면 요청 base_url 기반으로 계산."""
    env = (os.getenv("YOUTUBE_REDIRECT_URI_MUSIC") or "").strip()
    if env:
        return env
    return str(request.base_url).rstrip("/") + "/api/music/youtube/callback"


@router.get("/auth")
def auth(request: Request):
    """구글 OAuth 동의 화면으로 리다이렉트(음악 채널용)."""
    try:
        return RedirectResponse(build_auth_url(_redirect_uri(request)))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"음악 OAuth URL 생성 실패: {e}") from e


@router.get("/callback")
def callback(request: Request, code: str | None = None, error: str | None = None):
    """구글 콜백: 코드→토큰 교환→음악 채널 ID로 저장."""
    redir = _redirect_uri(request)
    if error:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "step": "google_oauth", "error": error, "redirect_uri": redir},
        )
    if not code:
        raise HTTPException(status_code=400, detail="code 파라미터가 없습니다.")

    try:
        result = exchange_code(code, redir)
    except Exception as e:  # noqa: BLE001
        logger.exception("[music-yt-callback] 토큰 교환 예외")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "step": "exchange_code", "error": repr(e), "redirect_uri": redir},
        )

    if not result.get("refresh_token"):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "step": "no_refresh_token", "error": result.get("error"),
                     "has_access_token": result.get("has_access_token"), "redirect_uri": redir},
        )
    save = result.get("save") or {}
    if not save.get("stored"):
        return JSONResponse(
            status_code=500,
            content={"ok": False, "step": "save", "supabase_error": save.get("supabase_error"),
                     "local_error": save.get("local_error"), "channel_id": result.get("channel_id")},
        )
    return JSONResponse(
        status_code=200,
        content={"ok": True, "step": "saved", "backend": save.get("backend"),
                 "channel_id": result.get("channel_id"),
                 "warning": save.get("supabase_error") and "Supabase 실패 — 로컬 폴백(휘발성)"},
    )


@router.get("/status")
def status():
    """음악 채널 연동 여부."""
    return {
        "connected": is_connected(),
        "channel_id": music_channel_id(),
        "channel_id_env": (os.getenv("YOUTUBE_CHANNEL_ID_MUSIC") or "").strip(),
    }
