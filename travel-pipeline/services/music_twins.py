"""쌍둥이 곡 묵혀 쓰기 (대표 2026-11-16).

Suno 1회 호출 = 같은 가사·스타일의 2클립(쌍둥이). 영상 1개에 1곡만 쓰므로 둘째 클립은
보관해 뒀다가 **최소 MUSIC_TWIN_MIN_AGE_DAYS(기본 7)일이 지난 뒤** 다른 날 영상으로 쓴다.
비슷한 곡 두 개가 붙어 나오면 이질감이 떨어진다는 대표 판단 — 바로 다음 회차에 쓰지 않는다.

- 저장: 생성 직후 둘째 클립의 맥락(가사·언어·장르·태그 조합 등)을 R2 JSON 으로 남긴다.
  (DB music_tracks 에는 원래부터 used=false 로 적립된다 — SQL 변경 없음.)
- 선택: 자동 회차(곡 수 1)가 시작할 때 그 채널의 묵힌 곡 중 가장 오래된 것 1개.
  맥락 JSON 이 없는 옛 적립 곡·짧은 곡·형식 불명 곡은 건너뛴다.
- 사용: 그날은 Suno 를 부르지 않고 그 곡으로 영상을 만든다(크레딧 0). 새 곡 날엔 다시 쌍둥이가 생긴다.

모든 실패는 None/무시 → 호출부가 평소처럼 새 곡을 만든다(제작을 절대 막지 않는다).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_CTX_KEYS = ("language", "lyrics", "title", "sub_theme", "core_message", "genre_id", "action",
             "tag_combo", "mood", "instrumental")


def enabled() -> bool:
    return (os.getenv("MUSIC_TWIN_REUSE") or "on").strip().lower() not in ("0", "off", "false", "no")


def min_age_days() -> float:
    try:
        return max(0.0, float((os.getenv("MUSIC_TWIN_MIN_AGE_DAYS") or "").strip() or 7))
    except ValueError:
        return 7.0


def save(channel: str | None, clip: dict, ctx: dict) -> bool:
    """둘째 클립의 맥락 저장. clip: {audio_id, ...}, ctx: 가사·언어·장르 등. 성공 여부."""
    if not enabled():
        return False
    aid = (clip or {}).get("audio_id")
    if not aid:
        return False
    try:
        from adapters import r2_storage
        if not r2_storage.is_available():
            return False
        data = {k: ctx.get(k) for k in _CTX_KEYS if ctx.get(k) not in (None, "")}
        data["saved_at"] = datetime.now(timezone.utc).isoformat()
        r2_storage.put_twin_ctx(channel or "rooftop_music", aid, data)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[twin] 쌍둥이 맥락 저장 실패(id=%s): %s", aid, e)
        return False


def pick(channel: str | None, *, now: datetime | None = None, exclude: set[str] | None = None) -> dict | None:
    """묵힌 지 min_age_days 이상 된 쌍둥이 1개(오래된 순) → 트랙+맥락 dict. 없으면 None. 사용 표시는 안 한다."""
    if not enabled():
        return None
    try:
        from adapters import r2_storage
        from services import music_store
        from services.music_produce import _MIN_DURATION_SEC
        now = now or datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=min_age_days())).isoformat()
        for row in music_store.list_aged_unused(channel, older_than_iso=cutoff):
            aid = row.get("audio_id") or row.get("id")
            if not aid or not row.get("r2_key") or aid in (exclude or set()):
                continue
            try:
                if row.get("duration") is not None and 0 < float(row["duration"]) < _MIN_DURATION_SEC:
                    continue
            except (TypeError, ValueError):
                pass
            ctx = r2_storage.get_twin_ctx(channel or "rooftop_music", aid)
            if not ctx or ctx.get("language") not in ("ko", "en", "inst"):
                continue   # 맥락 없는 옛 적립 곡 / 형식 불명 → 보컬·연주가 섞일 수 있어 쓰지 않는다
            if ctx["language"] != "inst" and not (ctx.get("lyrics") or "").strip():
                continue
            return {**ctx, "audio_id": aid, "r2_key": row["r2_key"], "duration": row.get("duration"),
                    "tags": row.get("tags") or "", "title": ctx.get("title") or row.get("title") or "",
                    "genre_id": ctx.get("genre_id") or row.get("genre"), "created_at": row.get("created_at")}
    except Exception as e:  # noqa: BLE001
        logger.warning("[twin] 묵힌 곡 조회 실패(channel=%s): %s", channel, e)
    return None


def consume(twin: dict) -> dict:
    """선택한 쌍둥이를 used=true 로 표시하고 produce 가 쓰는 트랙 rec 으로 바꾼다."""
    from services import music_store
    aid = twin["audio_id"]
    if not music_store.mark_track_used(aid):
        logger.warning("[twin] used 마킹 실패(id=%s) — 진행", aid)
    rec = {"audio_id": aid, "r2_key": twin["r2_key"], "duration": twin.get("duration"),
           "title": twin.get("title") or "", "tags": twin.get("tags") or "",
           "language": twin.get("language") or "ko"}
    if rec["language"] != "inst":
        rec.update(lyrics=twin.get("lyrics") or "", sub_theme=twin.get("sub_theme") or "",
                   core_message=twin.get("core_message") or "")
    return rec
