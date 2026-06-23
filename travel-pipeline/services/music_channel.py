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
