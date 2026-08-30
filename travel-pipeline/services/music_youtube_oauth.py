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

# ── 채널별 env 매핑(운동 채널 3단계) ────────────────────────────────────
# **기존 키 이름은 절대 바꾸지 않는다** — where 가 즉시 깨진다.
# 새 채널은 항목만 추가하면 된다.
_CHANNEL_ENV: dict[str, dict[str, str]] = {
    "rooftop_music": {
        "channel_id": "YOUTUBE_CHANNEL_ID_MUSIC",
        "refresh_token": "YOUTUBE_REFRESH_TOKEN_MUSIC",
    },
    "workout_music": {
        "channel_id": "YOUTUBE_CHANNEL_ID_WORKOUT",
        "refresh_token": "YOUTUBE_REFRESH_TOKEN_WORKOUT",
    },
}
DEFAULT_CHANNEL = "rooftop_music"


def is_valid_channel(channel: str | None) -> bool:
    """등록된 채널인지. callback 의 state 검증에 쓴다."""
    return isinstance(channel, str) and channel.strip() in _CHANNEL_ENV


def _resolve(channel: str | None) -> str:
    """None·빈값·미등록 → DEFAULT_CHANNEL. 예외를 던지지 않는다."""
    c = channel.strip() if isinstance(channel, str) else ""
    return c if c in _CHANNEL_ENV else DEFAULT_CHANNEL


def channel_id_env_key(channel: str | None = None) -> str:
    """해당 채널의 채널ID env 키 이름(오류 메시지에 그대로 쓴다)."""
    return _CHANNEL_ENV[_resolve(channel)]["channel_id"]


def configured_channel_id(channel: str | None = None) -> str:
    """해당 채널의 유튜브 채널 ID(env). **미설정이면 빈 문자열** — 폴백하지 않는다.

    where(기본)의 폴백 동작은 music_channel_id() 가 그대로 유지한다(회귀 0).
    운동 등 명시 채널은 자기 env 만 보고, 없으면 호출부가 업로드를 거부한다.
    """
    return (os.getenv(channel_id_env_key(channel)) or "").strip()


def music_channel_id(channel: str | None = None) -> str:
    """토큰 저장소 키 + 상태 표시용 채널 식별자.

    where 는 기존 동작 그대로 — env 미설정 시 리터럴 "music" 으로 떨어진다(회귀 0).
    다른 채널은 env 가 없으면 빈 문자열이 되고, 그 상태로는 토큰 조회·저장이
    무의미하므로 호출부가 먼저 거부한다.
    """
    ch = _resolve(channel)
    val = configured_channel_id(ch)
    if ch == DEFAULT_CHANNEL:
        return val or "music"
    return val


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


def build_auth_url(redirect_uri: str | None = None, *, channel: str | None = None) -> str:
    """구글 OAuth 동의 화면 URL(음악 채널용). access_type=offline+prompt=consent.

    channel: state 로 실어 보낸다 — 구글이 그대로 되돌려주므로 쿠키·세션 없이
    callback 까지 채널이 전달된다(OAuth 표준 방식).
    """
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
        "state": _resolve(channel),
    }
    logger.info(
        "[music-yt-oauth] 인증 URL 생성: redirect_uri=%s channel=%s", redir, _resolve(channel)
    )
    return f"{_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"


def exchange_code(code: str, redirect_uri: str | None = None, *, channel: str | None = None) -> dict:
    """인증 코드 → 토큰 교환 후 refresh_token 을 **해당 채널의** 채널 ID 키로 저장.

    Returns: {refresh_token, has_access_token, save, redirect_uri, channel, channel_id, error}
    """
    cid, cs = _client()
    redir = resolve_redirect_uri(redirect_uri)
    chan = _resolve(channel)
    ch = music_channel_id(chan)
    out: dict = {
        "refresh_token": None,
        "has_access_token": False,
        "redirect_uri": redir,
        "channel": chan,
        "channel_id": ch,
        "save": None,
        "error": None,
    }
    # 채널 ID env 가 없으면 토큰을 어떤 키로 저장할지 정할 수 없다 → 저장 자체를 막는다.
    # (잘못된 키로 저장되면 나중에 추적이 어렵다.)
    if not ch:
        out["error"] = (
            f"{channel_id_env_key(chan)} 미설정 — 채널 ID 를 먼저 환경변수에 넣어야 "
            "토큰을 올바른 키로 저장할 수 있습니다."
        )
        logger.warning("[music-yt-oauth] %s", out["error"])
        return out
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


def _music_refresh_token(channel: str | None = None) -> str | None:
    """해당 채널의 refresh_token: env(채널별 키) 우선, 없으면 저장소(채널 ID 키).

    env 우선은 where 의 기존 패턴 그대로 — 비상 수동 주입용이다.
    """
    ch = _resolve(channel)
    env_rt = (os.getenv(_CHANNEL_ENV[ch]["refresh_token"]) or "").strip()
    if env_rt:
        return env_rt
    key = music_channel_id(ch)
    return load_refresh_token(key) if key else None


def get_credentials(channel: str | None = None):
    """해당 채널 refresh_token 으로 access_token 을 갱신한 Credentials 반환(업로드용)."""
    from google.oauth2.credentials import Credentials

    ch = _resolve(channel)
    refresh_token = _music_refresh_token(ch)
    if not refresh_token:
        raise YouTubeNotConnected(
            f"유튜브 미연동(channel={ch}) — /music/settings 에서 이 채널을 연결하세요."
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


def is_connected(channel: str | None = None) -> bool:
    return bool(_music_refresh_token(channel))
