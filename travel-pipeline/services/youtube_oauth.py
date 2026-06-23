"""유튜브 OAuth 2.0 — requests 로 직접 구현(google-auth-oauthlib Flow 미사용, PKCE 미사용).

서버사이드 OAuth(confidential client: client_secret 보유) 표준.
처음 1회는 브라우저에서 /api/youtube/auth 로 구글 로그인해 refresh_token 을 발급받아
저장한다(youtube_tokens). 이후 업로드는 refresh_token 으로 access_token 을 갱신한다.

환경변수(Railway):
  YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REDIRECT_URI, YOUTUBE_CHANNEL_ID

OAuth URL/토큰 교환/토큰 갱신은 모두 requests 로 직접 호출한다(oauthlib Flow 의
PKCE 자동 주입·엄격 검증 회피). 업로드용 Credentials 객체만 google.oauth2 를 쓰며
(googleapiclient 가 요구), access_token 은 requests 로 갱신해 주입한다.
"""

from __future__ import annotations

import logging
import os
import urllib.parse

import requests

from services.youtube_tokens import load_refresh_token, save_refresh_token

logger = logging.getLogger(__name__)

# youtube.upload(업로드) + youtube(thumbnails.set 등) 권한.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    # #32 captions.insert(다국어 자막)에 필요. 추가 후 음악 채널 재인증 필요(force-ssl).
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_TIMEOUT = 30.0


class YouTubeNotConnected(RuntimeError):
    """refresh_token 이 없어 업로드 불가 — /api/youtube/auth 로 먼저 인증 필요."""


def _channel_id() -> str:
    return (os.getenv("YOUTUBE_CHANNEL_ID") or "default").strip() or "default"


def _oauth_env() -> tuple[str, str, str]:
    """(client_id, client_secret, redirect_uri). 하나라도 없으면 RuntimeError."""
    cid = (os.getenv("YOUTUBE_CLIENT_ID") or "").strip()
    cs = (os.getenv("YOUTUBE_CLIENT_SECRET") or "").strip()
    redir = (os.getenv("YOUTUBE_REDIRECT_URI") or "").strip()
    if not (cid and cs and redir):
        raise RuntimeError(
            "YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REDIRECT_URI 미설정"
        )
    return cid, cs, redir


def redirect_uri() -> str:
    """설정된 OAuth 리다이렉트 URI(콜백 URL 재확인·디버그용)."""
    return (os.getenv("YOUTUBE_REDIRECT_URI") or "").strip()


def build_auth_url() -> str:
    """구글 OAuth 동의 화면 URL 을 직접 조립(PKCE 미포함).

    access_type=offline + prompt=consent 로 refresh_token 을 강제 발급받는다.
    """
    cid, _cs, redir = _oauth_env()
    params = {
        "client_id": cid,
        "redirect_uri": redir,
        "scope": " ".join(SCOPES),
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    url = f"{_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"
    logger.info("[yt-oauth] 인증 URL 생성(requests, no-PKCE): redirect_uri=%s", redir)
    return url


def exchange_code(code: str) -> dict:
    """인증 코드 → 토큰 교환(requests POST, PKCE 미포함) 후 refresh_token 저장.

    Returns: {refresh_token(실제값|None), has_access_token, save(저장결과),
              redirect_uri, channel_id, error}
    """
    cid, cs, redir = _oauth_env()
    ch = _channel_id()
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
    logger.info(
        "[yt-oauth] 토큰 교환 시작(requests): redirect_uri=%s channel=%s code_len=%d",
        redir, ch, len(code or ""),
    )
    try:
        resp = requests.post(_TOKEN_ENDPOINT, data=data, timeout=_TIMEOUT)
    except requests.RequestException as e:
        out["error"] = f"토큰 엔드포인트 요청 실패: {type(e).__name__}: {e}"
        logger.warning("[yt-oauth] %s", out["error"])
        return out

    if resp.status_code != 200:
        out["error"] = f"토큰 교환 실패 HTTP {resp.status_code}: {resp.text[:300]}"
        logger.warning("[yt-oauth] %s", out["error"])
        return out

    tok = resp.json()
    refresh_token = tok.get("refresh_token")
    out["has_access_token"] = bool(tok.get("access_token"))
    logger.info(
        "[yt-oauth] 토큰 교환 결과: access_token=%s refresh_token=%s",
        out["has_access_token"], bool(refresh_token),
    )
    if not refresh_token:
        out["error"] = (
            "refresh_token 을 받지 못했습니다(이미 승인된 계정일 수 있음). "
            "구글 계정 보안 > 타사 액세스에서 앱 권한 해제 후 다시 인증하세요."
        )
        logger.warning("[yt-oauth] %s", out["error"])
        return out
    out["refresh_token"] = refresh_token
    out["save"] = save_refresh_token(ch, refresh_token)
    logger.info("[yt-oauth] 저장 결과: %s", out["save"])
    return out


def _refresh_access_token(refresh_token: str) -> str:
    """refresh_token → access_token 갱신(requests POST, PKCE 미포함)."""
    cid, cs, _redir = _oauth_env()
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


def get_credentials():
    """저장된 refresh_token 으로 access_token 을 갱신한 Credentials 반환(업로드용).

    토큰 갱신은 requests 로 직접 수행하고, googleapiclient 가 요구하는 Credentials
    객체에 access_token 을 주입한다(google-auth-oauthlib Flow 미사용).
    """
    from google.oauth2.credentials import Credentials

    refresh_token = load_refresh_token(_channel_id())
    if not refresh_token:
        raise YouTubeNotConnected(
            "유튜브 미연동 — 먼저 /api/youtube/auth 로 인증하세요."
        )
    cid, cs, _redir = _oauth_env()
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
    """refresh_token 보유 여부(프론트 '연동됨' 표시용)."""
    return bool(load_refresh_token(_channel_id()))
