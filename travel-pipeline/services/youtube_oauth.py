"""유튜브 OAuth 2.0 인증 — 인증 URL 생성 / 코드 교환 / 자격증명 갱신.

처음 1회는 브라우저에서 /api/youtube/auth 로 구글 로그인해 refresh_token 을 발급받아
저장한다(youtube_tokens). 이후 업로드는 refresh_token 으로 access_token 을 자동 갱신해
재로그인이 필요 없다.

환경변수(Railway):
  YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REDIRECT_URI, YOUTUBE_CHANNEL_ID

google-auth / google-auth-oauthlib 사용(이미 requirements 에 있음). import 는 함수 안에서
지연 로딩해 라이브러리 미설치 환경에서도 모듈 import 가 깨지지 않게 한다.
"""

from __future__ import annotations

import logging
import os

from services.youtube_tokens import load_refresh_token, save_refresh_token

logger = logging.getLogger(__name__)

# youtube.upload(업로드) + youtube(thumbnails.set 등) 권한.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]
_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
_TOKEN_URI = "https://oauth2.googleapis.com/token"


class YouTubeNotConnected(RuntimeError):
    """refresh_token 이 없어 업로드 불가 — /api/youtube/auth 로 먼저 인증 필요."""


def _channel_id() -> str:
    return (os.getenv("YOUTUBE_CHANNEL_ID") or "default").strip() or "default"


def _client_config() -> tuple[dict, str]:
    cid = (os.getenv("YOUTUBE_CLIENT_ID") or "").strip()
    cs = (os.getenv("YOUTUBE_CLIENT_SECRET") or "").strip()
    redir = (os.getenv("YOUTUBE_REDIRECT_URI") or "").strip()
    if not (cid and cs and redir):
        raise RuntimeError(
            "YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REDIRECT_URI 미설정"
        )
    config = {
        "web": {
            "client_id": cid,
            "client_secret": cs,
            "auth_uri": _AUTH_URI,
            "token_uri": _TOKEN_URI,
            "redirect_uris": [redir],
        }
    }
    return config, redir


def build_auth_url() -> str:
    """구글 OAuth 동의 화면 URL. access_type=offline + prompt=consent 로 refresh_token 확보."""
    from google_auth_oauthlib.flow import Flow

    config, redir = _client_config()
    flow = Flow.from_client_config(config, scopes=SCOPES, redirect_uri=redir)
    auth_url, _ = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    return auth_url


def exchange_code(code: str) -> str:
    """인증 코드 → 토큰 교환 후 refresh_token 을 영구 저장하고 반환."""
    from google_auth_oauthlib.flow import Flow

    config, redir = _client_config()
    flow = Flow.from_client_config(config, scopes=SCOPES, redirect_uri=redir)
    flow.fetch_token(code=code)
    refresh_token = getattr(flow.credentials, "refresh_token", None)
    if not refresh_token:
        # prompt=consent 인데도 refresh_token 이 없으면 이미 승인된 계정일 수 있다.
        raise RuntimeError(
            "refresh_token 을 받지 못했습니다. 구글 계정 권한을 해제 후 다시 인증하세요."
        )
    save_refresh_token(_channel_id(), refresh_token)
    return refresh_token


def get_credentials():
    """저장된 refresh_token 으로 access_token 을 갱신한 Credentials 반환(업로드용)."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    refresh_token = load_refresh_token(_channel_id())
    if not refresh_token:
        raise YouTubeNotConnected(
            "유튜브 미연동 — 먼저 /api/youtube/auth 로 인증하세요."
        )
    cid = (os.getenv("YOUTUBE_CLIENT_ID") or "").strip()
    cs = (os.getenv("YOUTUBE_CLIENT_SECRET") or "").strip()
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=_TOKEN_URI,
        client_id=cid,
        client_secret=cs,
        scopes=SCOPES,
    )
    creds.refresh(Request())  # access_token 자동 발급/갱신
    return creds


def is_connected() -> bool:
    """refresh_token 보유 여부(프론트 '연동됨' 표시용)."""
    return bool(load_refresh_token(_channel_id()))
