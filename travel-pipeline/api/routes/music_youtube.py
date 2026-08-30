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
    DEFAULT_CHANNEL,
    build_auth_url,
    channel_id_env_key,
    configured_channel_id,
    exchange_code,
    is_connected,
    is_valid_channel,
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
def auth(request: Request, channel: str | None = None):
    """구글 OAuth 동의 화면으로 리다이렉트. channel 은 state 로 실어 보낸다.

    미지정 → where(기존 동작 그대로). 미등록 문자열은 400 으로 거부한다 —
    잘못된 키로 토큰이 저장되면 추적이 어렵다.
    """
    if channel is not None and not is_valid_channel(channel):
        raise HTTPException(status_code=400, detail=f"등록되지 않은 채널입니다: {channel!r}")
    ch = channel or DEFAULT_CHANNEL
    if not configured_channel_id(ch):
        raise HTTPException(
            status_code=400,
            detail=f"{channel_id_env_key(ch)} 미설정 — 채널 ID 를 먼저 환경변수에 넣어주세요.",
        )
    try:
        return RedirectResponse(build_auth_url(_redirect_uri(request), channel=ch))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"음악 OAuth URL 생성 실패: {e}") from e


@router.get("/callback")
def callback(
    request: Request,
    code: str | None = None,
    error: str | None = None,
    state: str | None = None,
):
    """구글 콜백: 코드→토큰 교환→**state 가 지목한 채널의** 채널 ID 키로 저장.

    state 검증: 값이 있는데 미등록 채널이면 저장하지 않고 400 으로 거부한다.
    state 가 아예 없으면(구버전 링크·수동 호출) where 로 본다 — 기존 동작 유지.
    """
    redir = _redirect_uri(request)
    if state is not None and not is_valid_channel(state):
        logger.warning("[music-yt-callback] 미등록 state 거부: %r", state)
        return JSONResponse(
            status_code=400,
            content={"ok": False, "step": "invalid_state", "state": state,
                     "error": "등록되지 않은 채널 state — 토큰을 저장하지 않았습니다."},
        )
    chan = state or DEFAULT_CHANNEL
    if error:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "step": "google_oauth", "error": error, "redirect_uri": redir},
        )
    if not code:
        raise HTTPException(status_code=400, detail="code 파라미터가 없습니다.")

    try:
        result = exchange_code(code, redir, channel=chan)
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
                 "channel": result.get("channel"),
                 "channel_id": result.get("channel_id"),
                 "warning": save.get("supabase_error") and "Supabase 실패 — 로컬 폴백(휘발성)"},
    )


@router.get("/status")
def status(channel: str | None = None):
    """채널별 유튜브 연동 여부. channel 미지정 → where(기존 응답과 동일).

    connected=False 면 UI 가 "유튜브 연결 필요" 로 보여준다.
    channel_id 가 빈 값이면 env 자체가 없는 것 — 연결 시도도 못 한다.
    """
    if channel is not None and not is_valid_channel(channel):
        raise HTTPException(status_code=400, detail=f"등록되지 않은 채널입니다: {channel!r}")
    ch = channel or DEFAULT_CHANNEL
    return {
        "connected": is_connected(ch),
        "channel": ch,
        "channel_id": music_channel_id(ch),
        "channel_id_env": configured_channel_id(ch),
        "channel_id_env_key": channel_id_env_key(ch),
    }
