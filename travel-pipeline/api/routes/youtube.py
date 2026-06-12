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
from fastapi.responses import RedirectResponse

from services.youtube_oauth import build_auth_url, exchange_code, is_connected

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
    """구글이 돌려준 코드를 토큰으로 교환해 저장하고 프론트로 리다이렉트한다."""
    if error:
        logger.warning("유튜브 OAuth 콜백 오류: %s", error)
        return RedirectResponse(_frontend_settings_url(False))
    if not code:
        raise HTTPException(status_code=400, detail="code 파라미터가 없습니다.")
    try:
        exchange_code(code)
    except Exception as e:  # noqa: BLE001
        logger.warning("유튜브 토큰 교환 실패: %s", e)
        return RedirectResponse(_frontend_settings_url(False))
    return RedirectResponse(_frontend_settings_url(True))


@router.get("/status")
def status():
    """연동 여부 반환."""
    return {
        "connected": is_connected(),
        "channel_id": (os.getenv("YOUTUBE_CHANNEL_ID") or "").strip(),
        "auto_publish": (os.getenv("YOUTUBE_AUTO_PUBLISH") or "").strip().lower() == "true",
    }
