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

import base64
import hashlib
import logging
import os
import secrets
import uuid

from services.youtube_tokens import load_refresh_token, save_refresh_token

logger = logging.getLogger(__name__)

# youtube.upload(업로드) + youtube(thumbnails.set 등) 권한.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]
_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
_TOKEN_URI = "https://oauth2.googleapis.com/token"

# PKCE 임시 저장소: state(UUID) → code_verifier. Railway 단일 컨테이너라 메모리 공유 OK.
# /auth 에서 저장, /callback 에서 꺼내 쓰고 삭제(무상태 state 전달 대신 서버사이드 보관).
_pkce_store: dict[str, str] = {}
_PKCE_STORE_CAP = 100  # in-flight 인증이 비정상 종료돼도 메모리 무한 증가 방지


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


def redirect_uri() -> str:
    """설정된 OAuth 리다이렉트 URI(콜백 URL 재확인·디버그용)."""
    return (os.getenv("YOUTUBE_REDIRECT_URI") or "").strip()


def generate_pkce() -> tuple[str, str, str]:
    """PKCE (verifier, challenge, state) 생성. challenge=base64url(SHA256(verifier)), S256.

    verifier 는 URL-safe 86자(RFC 7636 의 43~128자 범위). state 는 저장소 키용 UUID.
    """
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    state = uuid.uuid4().hex
    return verifier, challenge, state


def pop_pkce_verifier(state: str | None) -> str | None:
    """state 로 저장된 code_verifier 를 꺼내며 동시에 삭제(1회용)."""
    if not state:
        return None
    return _pkce_store.pop(state, None)


def build_auth_url() -> str:
    """구글 OAuth 동의 화면 URL(PKCE S256). access_type=offline+prompt=consent 로 refresh_token 확보.

    code_verifier 는 서버 메모리(_pkce_store)에 state(UUID) 키로 저장하고, URL 에는 state 만
    싣는다(콜백이 state 로 조회).
    """
    from google_auth_oauthlib.flow import Flow

    config, redir = _client_config()
    verifier, challenge, state = generate_pkce()
    if len(_pkce_store) >= _PKCE_STORE_CAP:
        _pkce_store.clear()  # 비정상 누적 방지(in-flight 인증은 드물고 짧다)
    _pkce_store[state] = verifier
    logger.info(
        "[yt-oauth] 인증 URL 생성: redirect_uri=%s state=%s (PKCE S256, store=%d)",
        redir, state, len(_pkce_store),
    )
    flow = Flow.from_client_config(config, scopes=SCOPES, redirect_uri=redir)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        code_challenge=challenge,
        code_challenge_method="S256",
        state=state,  # 서버사이드 저장소 키(코드 verifier 는 URL 에 노출되지 않음)
    )
    return auth_url


def exchange_code(code: str, code_verifier: str | None = None) -> dict:
    """인증 코드 → 토큰 교환 후 refresh_token 저장. 상세 결과 dict 반환.

    code_verifier(PKCE) 가 주어지면 토큰 교환 요청에 포함한다(S256 검증).
    Returns: {refresh_token(실제값|None), has_access_token, save(저장결과),
              redirect_uri, channel_id, error}
    """
    from google_auth_oauthlib.flow import Flow

    config, redir = _client_config()
    ch = _channel_id()
    logger.info(
        "[yt-oauth] 토큰 교환 시작: redirect_uri=%s channel=%s code_len=%d pkce=%s",
        redir, ch, len(code or ""), bool(code_verifier),
    )
    flow = Flow.from_client_config(config, scopes=SCOPES, redirect_uri=redir)
    if code_verifier:
        # google-auth-oauthlib Flow.fetch_token 은 flow.code_verifier 를 토큰 요청에 넣는다.
        flow.code_verifier = code_verifier
    flow.fetch_token(code=code)
    creds = flow.credentials
    refresh_token = getattr(creds, "refresh_token", None)
    has_access = bool(getattr(creds, "token", None))
    logger.info(
        "[yt-oauth] 토큰 교환 결과: access_token=%s refresh_token=%s",
        has_access, bool(refresh_token),
    )
    out: dict = {
        "refresh_token": refresh_token,
        "has_access_token": has_access,
        "redirect_uri": redir,
        "channel_id": ch,
        "save": None,
        "error": None,
    }
    if not refresh_token:
        # prompt=consent 인데도 refresh_token 이 없으면 이미 승인된 계정일 수 있다.
        out["error"] = (
            "refresh_token 을 받지 못했습니다(이미 승인된 계정일 수 있음). "
            "구글 계정 보안 > 타사 액세스에서 앱 권한 해제 후 다시 인증하세요."
        )
        logger.warning("[yt-oauth] %s", out["error"])
        return out
    out["save"] = save_refresh_token(ch, refresh_token)
    logger.info("[yt-oauth] 저장 결과: %s", out["save"])
    return out


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
