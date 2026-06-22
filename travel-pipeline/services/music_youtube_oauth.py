"""음악 채널(Revezen) 유튜브 OAuth — 백곰(youtube_oauth)과 완전 분리.

youtube_oauth.py 패턴을 그대로 따르되 채널 변수만 음악용으로 교체한다:
  - 채널 ID: YOUTUBE_CHANNEL_ID_MUSIC (토큰이 이 키로 저장돼 백곰과 자동 분리)
  - refresh_token: YOUTUBE_REFRESH_TOKEN_MUSIC(env 직접) 우선, 없으면 youtube_tokens 저장소
  - client_id/secret 는 백곰과 공유(YOUTUBE_CLIENT_ID/SECRET, 같은 Google 앱)
  - redirect_uri 는 음악 콜백(/api/music/youtube/callback) — 라우트가 계산해 전달하거나
    YOUTUBE_REDIRECT_URI_MUSIC env 사용.

백곰 youtube_oauth.py 는 0줄 변경(상수만 import 재사용).
"""

from __future__ import annotations

import logging
import os
import urllib.parse

import requests

from services.youtube_oauth import (
    SCOPES,
    YouTubeNotConnected,
    _AUTH_ENDPOINT,
    _TOKEN_ENDPOINT,
)
from services.youtube_tokens import load_refresh_token, save_refresh_token

logger = logging.getLogger(__name__)

_TIMEOUT = 30.0


def music_channel_id() -> str:
    return (os.getenv("YOUTUBE_CHANNEL_ID_MUSIC") or "music").strip() or "music"


def _client() -> tuple[str, str]:
    cid = (os.getenv("YOUTUBE_CLIENT_ID") or "").strip()
    cs = (os.getenv("YOUTUBE_CLIENT_SECRET") or "").strip()
    if not (cid and cs):
        raise RuntimeError("YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET 미설정")
    return cid, cs


def resolve_redirect_uri(explicit: str | None = None) -> str:
    """음악 콜백 redirect_uri. 라우트가 준 값 우선, 없으면 env YOUTUBE_REDIRECT_URI_MUSIC."""
    r = (explicit or os.getenv("YOUTUBE_REDIRECT_URI_MUSIC") or "").strip()
    if not r:
        raise RuntimeError(
            "음악 OAuth redirect_uri 미설정 — YOUTUBE_REDIRECT_URI_MUSIC 또는 라우트 전달 필요"
        )
    return r


def build_auth_url(redirect_uri: str | None = None) -> str:
    """구글 OAuth 동의 화면 URL(음악 채널용). access_type=offline+prompt=consent."""
    cid, _cs = _client()
    redir = resolve_redirect_uri(redirect_uri)
    params = {
        "client_id": cid,
        "redirect_uri": redir,
        "scope": " ".join(SCOPES),
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    logger.info("[music-yt-oauth] 인증 URL 생성: redirect_uri=%s", redir)
    return f"{_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"


def exchange_code(code: str, redirect_uri: str | None = None) -> dict:
    """인증 코드 → 토큰 교환 후 refresh_token 을 음악 채널 ID 로 저장.

    Returns: {refresh_token, has_access_token, save, redirect_uri, channel_id, error}
    """
    cid, cs = _client()
    redir = resolve_redirect_uri(redirect_uri)
    ch = music_channel_id()
    out: dict = {
        "refresh_token": None,
        "has_access_token": False,
        "redirect_uri": redir,
        "channel_id": ch,
        "save": None,
        "error": None,
    }
    data = {
        "code": code,
        "client_id": cid,
        "client_secret": cs,
        "redirect_uri": redir,
        "grant_type": "authorization_code",
    }
    logger.info("[music-yt-oauth] 토큰 교환 시작: channel=%s", ch)
    try:
        resp = requests.post(_TOKEN_ENDPOINT, data=data, timeout=_TIMEOUT)
    except requests.RequestException as e:
        out["error"] = f"토큰 엔드포인트 요청 실패: {type(e).__name__}: {e}"
        logger.warning("[music-yt-oauth] %s", out["error"])
        return out
    if resp.status_code != 200:
        out["error"] = f"토큰 교환 실패 HTTP {resp.status_code}: {resp.text[:300]}"
        logger.warning("[music-yt-oauth] %s", out["error"])
        return out

    tok = resp.json()
    refresh_token = tok.get("refresh_token")
    out["has_access_token"] = bool(tok.get("access_token"))
    if not refresh_token:
        out["error"] = (
            "refresh_token 을 받지 못했습니다(이미 승인된 계정일 수 있음). "
            "구글 계정 보안 > 타사 액세스에서 앱 권한 해제 후 다시 인증하세요."
        )
        logger.warning("[music-yt-oauth] %s", out["error"])
        return out
    out["refresh_token"] = refresh_token
    out["save"] = save_refresh_token(ch, refresh_token)
    logger.info("[music-yt-oauth] 저장 결과: %s", out["save"])
    return out


def _refresh_access_token(refresh_token: str) -> str:
    cid, cs = _client()
    data = {
        "client_id": cid,
        "client_secret": cs,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    resp = requests.post(_TOKEN_ENDPOINT, data=data, timeout=_TIMEOUT)
    if resp.status_code != 200:
        raise RuntimeError(
            f"access_token 갱신 실패 HTTP {resp.status_code}: {resp.text[:300]}"
        )
    access_token = resp.json().get("access_token")
    if not access_token:
        raise RuntimeError("access_token 갱신 응답에 access_token 이 없습니다.")
    return access_token


def _music_refresh_token() -> str | None:
    """음악 refresh_token: env YOUTUBE_REFRESH_TOKEN_MUSIC 우선, 없으면 저장소."""
    env_rt = (os.getenv("YOUTUBE_REFRESH_TOKEN_MUSIC") or "").strip()
    return env_rt or load_refresh_token(music_channel_id())


def get_credentials():
    """음악 채널 refresh_token 으로 access_token 을 갱신한 Credentials 반환(업로드용)."""
    from google.oauth2.credentials import Credentials

    refresh_token = _music_refresh_token()
    if not refresh_token:
        raise YouTubeNotConnected(
            "음악 유튜브 미연동 — 먼저 /api/music/youtube/auth 로 인증하세요."
        )
    cid, cs = _client()
    access_token = _refresh_access_token(refresh_token)
    return Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=_TOKEN_ENDPOINT,
        client_id=cid,
        client_secret=cs,
        scopes=SCOPES,
    )


def is_connected() -> bool:
    return bool(_music_refresh_token())
