"""음악 유튜브 업로드/검토 큐 저장소 (Supabase music_uploads).

흐름(#8 검토 대기 큐):
  영상 생성 → record_pending(status='pending', mp4_url·gpt_prompt 등)
  → 대시보드에서 썸네일 업로드 → set_thumbnail
  → 공개 업로드 → record_upload(status='uploaded', youtube_url) (썸네일 게이트는 라우트에서)

music_store 의 PostgREST(httpx) 패턴을 재사용(신규 의존성 0). mix_id 유니크 기준 upsert.
⚠️ music_uploads 테이블/컬럼은 GRANT 필요(docs/music_uploads.sql + music_uploads_v2.sql).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from services.music_store import _http_err, _supabase_cfg

logger = logging.getLogger(__name__)

_TABLE = "music_uploads"
_KST = timezone(timedelta(hours=9))
_SELECT = (
    "slug,mix_id,title_kr,genre,mood,tag_combo,mp4_url,gpt_prompt,thumbnail_r2_key,character_r2_key,viz_spec,"
    "localizations,show_playlist,status,youtube_video_id,youtube_url,channel,created_at"
)


def _resolve_channel(channel: str | None) -> str:
    """music_channel.resolve_channel 지연 호출(순환 import 회피)."""
    from services.music_channel import resolve_channel

    return resolve_channel(channel)


def _headers(key: str, *, upsert: bool = False, patch: bool = False) -> dict:
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if upsert:
        h["Prefer"] = "resolution=merge-duplicates"
    if patch:
        h["Prefer"] = "return=representation"
    return h


def record_pending(
    slug: str,
    mix_id: str,
    *,
    mp4_url: str,
    title_kr: str = "",
    genre: str = "",
    mood: str = "",
    tag_combo: dict | None = None,
    gpt_prompt: str = "",
    thumbnail_r2_key: str | None = None,
    viz_spec: dict | None = None,
    channel: str | None = None,
) -> dict:
    """영상 생성 완료 → 검토 대기(pending) 행 upsert(mix_id 기준). {stored, error}.

    channel=None 이면 키를 아예 넣지 않아 DB default('rooftop_music')가 적용된다.
    (렌더 경로 music_video.py 는 수정 금지 파일이라 채널을 못 넘긴다 → 호출부가
     렌더 직후 set_channel 로 보정한다. music_manual.run / music_library.run 참조.)

    thumbnail_r2_key: 첫프레임 자동 썸네일(#20) 키. 주면 공개 업로드 게이트가 자동 충족.
    viz_spec: 곡 분석 결과(#20) 캐시 — 같은 mix 재렌더 시 재사용.
    tag_combo: 8축 태그 조합(jsonb). 카드에 한글 칩 나열용.
    """
    url, key = _supabase_cfg()
    if not (url and key):
        logger.warning("[music-uploads] SUPABASE 미설정 — pending 기록 생략")
        return {"stored": False, "error": "supabase 미설정"}
    record = {
        "slug": slug,
        "mix_id": mix_id,
        "title_kr": title_kr,
        "genre": genre,
        "mood": mood,
        "mp4_url": mp4_url,
        "gpt_prompt": gpt_prompt,
        "status": "pending",
    }
    if tag_combo is not None:
        record["tag_combo"] = tag_combo
    if thumbnail_r2_key:
        record["thumbnail_r2_key"] = thumbnail_r2_key
    if viz_spec is not None:
        record["viz_spec"] = viz_spec
    if channel:
        record["channel"] = _resolve_channel(channel)
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.post(
                f"{url}/rest/v1/{_TABLE}?on_conflict=mix_id",
                headers=_headers(key, upsert=True),
                json=[record],
            )
            r.raise_for_status()
        logger.info("[music-uploads] pending 기록 OK (mix_id=%s)", mix_id)
        return {"stored": True, "error": None}
    except Exception as e:  # noqa: BLE001
        msg = _http_err(e)
        logger.warning("[music-uploads] pending 기록 실패(mix_id=%s): %s", mix_id, msg)
        return {"stored": False, "error": msg}


def delete_pending(mix_id: str) -> dict:
    """단일 mix_id 큐 행만 삭제(다른 행 영향 0). {deleted:int, error}.

    mix_id=eq 필터로 정확히 한 행만 대상으로 한다. Prefer: return=representation 으로
    실제 삭제된 행 수를 확인한다. R2 파일은 만료 정책에 맡기고 즉시 지우지 않는다(안전).
    """
    url, key = _supabase_cfg()
    if not (url and key):
        return {"deleted": 0, "error": "supabase 미설정"}
    if not (mix_id or "").strip():
        return {"deleted": 0, "error": "mix_id 필요"}
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.delete(
                f"{url}/rest/v1/{_TABLE}",
                headers={**_headers(key), "Prefer": "return=representation"},
                params={"mix_id": f"eq.{mix_id}"},
            )
            r.raise_for_status()
            rows = r.json() if r.content else []
        n = len(rows) if isinstance(rows, list) else 0
        logger.info("[music-uploads] 삭제 OK (mix_id=%s, %d행)", mix_id, n)
        return {"deleted": n, "error": None}
    except Exception as e:  # noqa: BLE001
        msg = _http_err(e)
        logger.warning("[music-uploads] 삭제 실패(mix_id=%s): %s", mix_id, msg)
        return {"deleted": 0, "error": msg}


def list_pending(*, channel: str | None = None) -> list[dict]:
    """검토 대기(status=pending) 목록 최신순. 미설정/오류 시 빈 리스트.

    channel=None → DEFAULT_CHANNEL(where). 마이그레이션이 기존 행을 where 로 백필하므로
    지금 시점의 결과 집합은 변하지 않는다.
    """
    url, key = _supabase_cfg()
    if not (url and key):
        return []
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.get(
                f"{url}/rest/v1/{_TABLE}",
                headers=_headers(key),
                params={
                    "status": "eq.pending",
                    "channel": f"eq.{_resolve_channel(channel)}",
                    "select": _SELECT,
                    "order": "created_at.desc",
                },
            )
            r.raise_for_status()
            rows = r.json()
        return rows if isinstance(rows, list) else []
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-uploads] 큐 조회 실패: %s", _http_err(e))
        return []


def get_upload(mix_id: str) -> dict | None:
    """mix_id 로 업로드 행 1개 조회. 없으면 None."""
    url, key = _supabase_cfg()
    if not (url and key):
        return None
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.get(
                f"{url}/rest/v1/{_TABLE}",
                headers=_headers(key),
                params={"mix_id": f"eq.{mix_id}", "select": _SELECT, "limit": "1"},
            )
            r.raise_for_status()
            rows = r.json()
        return rows[0] if rows else None
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-uploads] 행 조회 실패(mix_id=%s): %s", mix_id, _http_err(e))
        return None


def get_viz_spec(mix_id: str) -> dict | None:
    """mix_id 의 캐시된 곡 분석(viz_spec) 조회(#20). 없으면 None."""
    row = get_upload(mix_id)
    if not row:
        return None
    spec = row.get("viz_spec")
    return spec if isinstance(spec, dict) and spec else None


def count_today_kst(*, channel: str | None = None) -> int:
    """오늘(KST 자정 이후) 생성된 music_uploads row 수 — cron 중복 생성 스킵 판단용(#28).

    created_at >= KST 자정(UTC 환산) 으로 필터. Prefer: count=exact 의 Content-Range 로
    총개수만 받는다(전체 fetch 회피). 미설정/오류 시 0(→ 호출부가 생성 진행, 안전).

    channel=None → DEFAULT_CHANNEL(where). ※ cron 선점 로직(api/routes/music.py:147)은
    이번에 건드리지 않는다(3단계) — 인자만 받을 수 있게 열어둔다.
    """
    url, key = _supabase_cfg()
    if not (url and key):
        return 0
    now = datetime.now(_KST)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    since = midnight.astimezone(timezone.utc).isoformat()
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.get(
                f"{url}/rest/v1/{_TABLE}",
                headers={**_headers(key), "Prefer": "count=exact"},
                params={
                    "created_at": f"gte.{since}",
                    "channel": f"eq.{_resolve_channel(channel)}",
                    "select": "mix_id",
                    "limit": "1",
                },
            )
            r.raise_for_status()
            cr = r.headers.get("content-range", "")  # 예: "0-0/3"
            if "/" in cr:
                total = cr.rsplit("/", 1)[-1]
                if total.isdigit():
                    return int(total)
            rows = r.json()
            return len(rows) if isinstance(rows, list) else 0
    except Exception as e:  # noqa: BLE001 - 조회 실패 시 0(생성 진행, 안전)
        logger.warning("[music-uploads] 오늘 생성 수 조회 실패: %s", _http_err(e))
        return 0


def list_uploaded(limit: int = 12, *, channel: str | None = None) -> list[dict]:
    """공개 업로드 완료(status=uploaded) 목록 최신순 — 대시보드 '최근 업로드' 마퀴용.

    channel=None → DEFAULT_CHANNEL(where).
    """
    url, key = _supabase_cfg()
    if not (url and key):
        return []
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.get(
                f"{url}/rest/v1/{_TABLE}",
                headers=_headers(key),
                params={
                    "status": "eq.uploaded", "select": _SELECT,
                    "channel": f"eq.{_resolve_channel(channel)}",
                    "order": "created_at.desc", "limit": str(limit),
                },
            )
            r.raise_for_status()
            rows = r.json()
        return rows if isinstance(rows, list) else []
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-uploads] 업로드 목록 조회 실패: %s", _http_err(e))
        return []


def set_channel(mix_id: str, channel: str | None) -> dict:
    """채널 축 보정(PATCH). {stored, error}.

    렌더 경로(music_video.make_video → record_pending)는 수정 금지 파일이라 채널을
    넘길 수 없다. 그래서 렌더를 시킨 쪽(music_manual.run / music_library.run)이
    렌더 직후 mix_id 로 이 함수를 불러 채널을 박는다. best-effort — 실패해도 영상은
    이미 만들어졌으므로 흐름을 막지 않는다(where 큐에 남을 뿐).
    """
    ch = _resolve_channel(channel)
    url, key = _supabase_cfg()
    if not (url and key):
        return {"stored": False, "error": "supabase 미설정"}
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.patch(
                f"{url}/rest/v1/{_TABLE}?mix_id=eq.{mix_id}",
                headers=_headers(key, patch=True),
                json={"channel": ch},
            )
            r.raise_for_status()
        return {"stored": True, "error": None}
    except Exception as e:  # noqa: BLE001
        msg = _http_err(e)
        logger.warning("[music-uploads] channel 보정 실패(mix_id=%s): %s", mix_id, msg)
        return {"stored": False, "error": msg}


def set_thumbnail(mix_id: str, thumbnail_r2_key: str) -> dict:
    """썸네일 R2 키 업데이트(PATCH). {stored, error}."""
    url, key = _supabase_cfg()
    if not (url and key):
        return {"stored": False, "error": "supabase 미설정"}
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.patch(
                f"{url}/rest/v1/{_TABLE}?mix_id=eq.{mix_id}",
                headers=_headers(key, patch=True),
                json={"thumbnail_r2_key": thumbnail_r2_key},
            )
            r.raise_for_status()
        return {"stored": True, "error": None}
    except Exception as e:  # noqa: BLE001
        return {"stored": False, "error": _http_err(e)}


def set_show_playlist(mix_id: str, show: bool) -> dict:
    """영상별 PLAY LIST 표시 토글 저장(#39, PATCH). {stored, error}."""
    url, key = _supabase_cfg()
    if not (url and key):
        return {"stored": False, "error": "supabase 미설정"}
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.patch(
                f"{url}/rest/v1/{_TABLE}?mix_id=eq.{mix_id}",
                headers=_headers(key, patch=True),
                json={"show_playlist": bool(show)},
            )
            r.raise_for_status()
        return {"stored": True, "error": None}
    except Exception as e:  # noqa: BLE001
        return {"stored": False, "error": _http_err(e)}


def set_localizations(mix_id: str, localizations: dict) -> dict:
    """다국어 데이터(#32) jsonb 저장/수정(PATCH). {stored, error}.

    localizations 구조: {meta:{lang:{title,description}}, lyrics:{lang:text}, hashtags:[...], source_lang}.
    """
    url, key = _supabase_cfg()
    if not (url and key):
        return {"stored": False, "error": "supabase 미설정"}
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.patch(
                f"{url}/rest/v1/{_TABLE}?mix_id=eq.{mix_id}",
                headers=_headers(key, patch=True),
                json={"localizations": localizations},
            )
            r.raise_for_status()
        return {"stored": True, "error": None}
    except Exception as e:  # noqa: BLE001
        return {"stored": False, "error": _http_err(e)}


def set_character(mix_id: str, character_r2_key: str) -> dict:
    """#50 인물 이미지 R2 키 업데이트(PATCH). {stored, error}."""
    url, key = _supabase_cfg()
    if not (url and key):
        return {"stored": False, "error": "supabase 미설정"}
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.patch(
                f"{url}/rest/v1/{_TABLE}?mix_id=eq.{mix_id}",
                headers=_headers(key, patch=True),
                json={"character_r2_key": character_r2_key},
            )
            r.raise_for_status()
        return {"stored": True, "error": None}
    except Exception as e:  # noqa: BLE001
        return {"stored": False, "error": _http_err(e)}


def clear_character(mix_id: str) -> dict:
    """#50 인물 제거 — character_r2_key='' (PATCH). R2 파일은 만료/덮어쓰기에 위임."""
    url, key = _supabase_cfg()
    if not (url and key):
        return {"stored": False, "error": "supabase 미설정"}
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.patch(
                f"{url}/rest/v1/{_TABLE}?mix_id=eq.{mix_id}",
                headers=_headers(key, patch=True),
                json={"character_r2_key": ""},
            )
            r.raise_for_status()
        return {"stored": True, "error": None}
    except Exception as e:  # noqa: BLE001
        return {"stored": False, "error": _http_err(e)}


def clear_localizations(mix_id: str) -> dict:
    """localizations 캐시 초기화(PATCH null) — 재렌더 시 호출해 다국어 강제 재생성 유도."""
    url, key = _supabase_cfg()
    if not (url and key):
        return {"stored": False, "error": "supabase 미설정"}
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.patch(
                f"{url}/rest/v1/{_TABLE}?mix_id=eq.{mix_id}",
                headers=_headers(key, patch=True),
                json={"localizations": None},
            )
            r.raise_for_status()
        return {"stored": True, "error": None}
    except Exception as e:  # noqa: BLE001
        return {"stored": False, "error": _http_err(e)}


def clear_thumbnail(mix_id: str) -> dict:
    """업로드한 이미지 제거(#33 C) — thumbnail_r2_key=null(PATCH). R2 파일은 만료에 위임."""
    url, key = _supabase_cfg()
    if not (url and key):
        return {"stored": False, "error": "supabase 미설정"}
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.patch(
                f"{url}/rest/v1/{_TABLE}?mix_id=eq.{mix_id}",
                headers=_headers(key, patch=True),
                json={"thumbnail_r2_key": None},
            )
            r.raise_for_status()
        return {"stored": True, "error": None}
    except Exception as e:  # noqa: BLE001
        return {"stored": False, "error": _http_err(e)}


def get_localizations(mix_id: str) -> dict | None:
    """저장된 다국어 데이터 조회. 없으면 None."""
    row = get_upload(mix_id)
    if not row:
        return None
    loc = row.get("localizations")
    return loc if isinstance(loc, dict) and loc else None


def record_upload(slug: str, mix_id: str, youtube_video_id: str, youtube_url: str) -> dict:
    """공개 업로드 완료 기록 — status=uploaded 로 upsert(mix_id 기준). {stored, error}.

    pending 행이 있으면 그 행을 uploaded 로 갱신(썸네일/gpt_prompt 등은 보존),
    없으면(run_theme 직접 업로드 경로) 새 행을 만든다.
    """
    url, key = _supabase_cfg()
    if not (url and key):
        logger.warning("[music-uploads] SUPABASE 미설정 — 업로드 기록 생략")
        return {"stored": False, "error": "supabase 미설정"}
    record = {
        "slug": slug,
        "mix_id": mix_id,
        "youtube_video_id": youtube_video_id,
        "youtube_url": youtube_url,
        "status": "uploaded",
    }
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.post(
                f"{url}/rest/v1/{_TABLE}?on_conflict=mix_id",
                headers=_headers(key, upsert=True),
                json=[record],
            )
            r.raise_for_status()
        logger.info("[music-uploads] uploaded 기록 OK (video_id=%s)", youtube_video_id)
        return {"stored": True, "error": None}
    except Exception as e:  # noqa: BLE001
        msg = _http_err(e)
        logger.warning("[music-uploads] uploaded 기록 실패(video_id=%s): %s", youtube_video_id, msg)
        return {"stored": False, "error": msg}
