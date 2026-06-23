"""음악 채널 상태(channel_status) 읽기 — cron 이 곡수(track_count)를 읽는다(#30).

대시보드 토글이 channel_status(channel_id='rooftop_music')에 저장한 track_count 를
music cron(_run_produce)이 읽어 run_theme(n=track_count) 로 생성한다. 백곰과 같은
channel_status 테이블을 쓰되 channel_id 로 분리(같은 컬럼 재사용).
"""

from __future__ import annotations

import logging

import httpx

from services.music_store import _http_err, _supabase_cfg

logger = logging.getLogger(__name__)

MUSIC_CHANNEL_ID = "rooftop_music"
_TABLE = "channel_status"
_MIN, _MAX = 1, 50  # #34 곡수 1~50
DEFAULT_TRACK_COUNT = 1


def _clamp(n: int) -> int:
    return max(_MIN, min(_MAX, n))


def get_track_count(default: int = DEFAULT_TRACK_COUNT) -> int:
    """음악 채널 곡수(1~8). 미설정/오류 시 default(=1). 안전 기본(과금 최소)."""
    url, key = _supabase_cfg()
    if not (url and key):
        return default
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(
                f"{url}/rest/v1/{_TABLE}",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                params={"channel_id": f"eq.{MUSIC_CHANNEL_ID}", "select": "track_count", "limit": "1"},
            )
            r.raise_for_status()
            rows = r.json()
        if not rows:
            return default
        tc = rows[0].get("track_count")
        return _clamp(int(tc)) if tc is not None else default
    except Exception as e:  # noqa: BLE001 - 조회 실패 시 안전 기본(1)
        logger.warning("[music-channel] track_count 조회 실패(기본 %d): %s", default, _http_err(e))
        return default


# #37 채널 설정(슬로건·소셜·AI 명시) — channel_status.channel_config jsonb. 기본 AI 명시 문구 제공.
DEFAULT_AI_DISCLOSURE = (
    "💿 모든 음악은 AI 음원 생성 시스템으로 제작한 창작 사운드입니다. "
    "모든 이미지는 AI 생성 또는 라이선스 이미지를 사용합니다."
)
_CONFIG_KEYS = (
    "slogan_en", "slogan_kr", "email", "instagram", "tiktok", "spotify_url", "ai_disclosure",
)


def default_channel_config() -> dict:
    """빈 채널 설정(AI 명시만 기본값 채움). 프론트/백엔드 공통 기본."""
    return {k: (DEFAULT_AI_DISCLOSURE if k == "ai_disclosure" else "") for k in _CONFIG_KEYS}


def get_channel_config() -> dict:
    """음악 채널 설정(channel_config) 조회. 미설정/오류/컬럼 미존재 시 기본값(빈 칸 + 기본 AI 명시).

    공개 업로드 본문 조립(music_meta.build_description)에서 사용. 빈 값은 해당 섹션 생략.
    """
    base = default_channel_config()
    url, key = _supabase_cfg()
    if not (url and key):
        return base
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.get(
                f"{url}/rest/v1/{_TABLE}",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                params={"channel_id": f"eq.{MUSIC_CHANNEL_ID}", "select": "channel_config", "limit": "1"},
            )
            r.raise_for_status()
            rows = r.json()
        cfg = (rows[0].get("channel_config") if rows else None) or {}
        if isinstance(cfg, dict):
            for k in _CONFIG_KEYS:
                v = cfg.get(k)
                if isinstance(v, str) and v.strip():
                    base[k] = v.strip()
        return base
    except Exception as e:  # noqa: BLE001 - 컬럼 미존재/오류 시 기본값
        logger.warning("[music-channel] channel_config 조회 실패(기본값 사용): %s", _http_err(e))
        return base
