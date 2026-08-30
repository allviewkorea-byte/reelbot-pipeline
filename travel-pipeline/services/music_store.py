"""음악 트랙(Rooftop Music) 메타 영구 저장소.

sunoapi.org 로 생성·R2 보관한 곡의 메타데이터를 Supabase `music_tracks` 테이블에
기록한다. Supabase 파이썬 SDK 없이 PostgREST(REST) 를 httpx 로 직접 호출한다
(신규 의존성 없음 — youtube_tokens.py 와 동일 패턴).

환경변수(프론트 lib/supabase 와 동일 네이밍):
  SUPABASE_URL          — 프로젝트 URL
  SUPABASE_SECRET_KEY   — service role(secret) 키 (대안: SUPABASE_SERVICE_ROLE_KEY / SUPABASE_KEY)

⚠️ 테이블은 GRANT 가 필요하다(레포에 마이그레이션 파일이 없어 Supabase SQL 에디터에서
수동 실행). docs/music_tracks.sql 참고:
  create table if not exists music_tracks (
    id text primary key,            -- audio_id (곡 단위 고유)
    theme_slug text not null,
    task_id text,
    audio_id text,
    title text,
    tags text,
    duration numeric,
    r2_key text,
    status text,
    used boolean not null default false,   -- #46: 영상에 사용됨(true=소진) / false=재활용 가능
    genre text not null default '',         -- #46: 장르 id(예: citypop). 빈값=레거시(재활용 제외)
    action text not null default '',       -- 어떨때 id(예: sleep, study). 빈값=레거시(태그 없이 생성)
    created_at timestamptz default now()
  );
  grant all on table music_tracks to service_role, anon, authenticated;
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_TABLE = "music_tracks"


def _supabase_cfg() -> tuple[str | None, str | None]:
    url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    key = (
        os.getenv("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or ""
    ).strip()
    return (url or None, key or None)


def _http_err(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        return f"HTTP {e.response.status_code}: {e.response.text[:300]}"
    return f"{type(e).__name__}: {e}"


def is_available() -> bool:
    url, key = _supabase_cfg()
    return bool(url and key)


def _resolve_channel(channel: str | None) -> str:
    """music_channel.resolve_channel 지연 호출.

    music_channel 이 이 모듈(_supabase_cfg/_http_err)을 import 하므로 모듈 최상단에서
    맞import 하면 순환이 된다. 함수 안에서 늦게 가져온다.
    """
    from services.music_channel import resolve_channel

    return resolve_channel(channel)


def upsert_track(record: dict) -> dict:
    """곡 메타 1행을 upsert(id 충돌 시 병합). 결과 dict 반환.

    record: {id, theme_slug, task_id, audio_id, title, tags, duration, r2_key, status}
    id(=audio_id) 로 멱등 — 폴링/콜백 양쪽이 같은 곡을 기록해도 1행만 남는다.
    record 에 channel 이 없으면 DEFAULT_CHANNEL(where)로 채워 저장한다 → 채널을 안 넘기는
    기존 호출부의 트랙은 전부 where 풀에 쌓인다(회귀 0).
    Returns: {stored: bool, error: str|None}
    """
    record = dict(record or {})
    record["channel"] = _resolve_channel(record.get("channel"))
    url, key = _supabase_cfg()
    if not (url and key):
        logger.warning("[music-db] SUPABASE_URL / SUPABASE_SECRET_KEY 미설정 — DB 기록 생략")
        return {"stored": False, "error": "supabase 미설정"}
    try:
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",  # upsert
        }
        with httpx.Client(timeout=30.0) as c:
            r = c.post(
                f"{url}/rest/v1/{_TABLE}?on_conflict=id",
                headers=headers,
                json=[record],
            )
            r.raise_for_status()
        logger.info("[music-db] 저장 OK (id=%s)", record.get("id"))
        return {"stored": True, "error": None}
    except Exception as e:  # noqa: BLE001
        msg = _http_err(e)
        logger.warning("[music-db] 저장 실패(id=%s): %s", record.get("id"), msg)
        return {"stored": False, "error": msg}


def list_tracks(
    theme_slug: str, *, status: str | None = "SUCCESS", channel: str | None = None
) -> list[dict]:
    """테마의 곡 목록을 created_at 오름차순으로 조회(믹스 입력용).

    status 를 주면 해당 상태만(기본 SUCCESS). Supabase 미설정/오류 시 빈 리스트.

    ★ channel=None 은 여기서만 **무필터**를 뜻한다(다른 함수처럼 DEFAULT_CHANNEL 로
      해석하지 않는다). theme_slug 는 제작 런마다 고유해 이미 채널까지 좁혀지는데,
      기본을 where 로 잡으면 운동 채널 런(channel=workout_music)의 트랙이 전부
      걸러져 마스터링·믹스가 빈 목록을 받는다. 호출부(music_master/music_mix)는
      채널을 넘기지 않으므로 기본 무필터가 유일하게 안전한 선택이다.
    """
    url, key = _supabase_cfg()
    if not (url and key):
        logger.warning("[music-db] SUPABASE 미설정 — 곡 조회 생략")
        return []
    try:
        headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        params = {
            "theme_slug": f"eq.{theme_slug}",
            "select": "id,theme_slug,task_id,audio_id,title,tags,duration,r2_key,status,channel,created_at",
            "order": "created_at.asc",
        }
        if status:
            params["status"] = f"eq.{status}"
        if channel:  # 명시했을 때만 필터(위 docstring 참조)
            params["channel"] = f"eq.{_resolve_channel(channel)}"
        with httpx.Client(timeout=30.0) as c:
            r = c.get(f"{url}/rest/v1/{_TABLE}", headers=headers, params=params)
            r.raise_for_status()
            rows = r.json()
        return rows if isinstance(rows, list) else []
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-db] 곡 조회 실패(theme=%s): %s", theme_slug, _http_err(e))
        return []


# ── 음원 라이브러리(#48) — 적립곡 목록·조회·통계 ───────────────────────
_LIBRARY_SELECT = (
    "id,theme_slug,task_id,audio_id,title,tags,duration,r2_key,status,used,genre,action,"
    "channel,created_at"
)


def list_library(
    *, genre: str | None = None, action: str | None = None, used: bool | None = None,
    limit: int = 100, offset: int = 0, channel: str | None = None,
) -> list[dict]:
    """적립곡(SUCCESS) 목록을 최신순으로 조회. genre/action/used 필터 선택. 미설정/오류 시 빈 리스트.

    channel=None → DEFAULT_CHANNEL(where). 마이그레이션이 기존 행을 전부 where 로
    백필하므로 지금 시점의 결과 집합은 변하지 않는다.
    """
    url, key = _supabase_cfg()
    if not (url and key):
        logger.warning("[music-db] SUPABASE 미설정 — 라이브러리 조회 생략")
        return []
    try:
        headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        params = {
            "select": _LIBRARY_SELECT,
            "status": "eq.SUCCESS",
            "channel": f"eq.{_resolve_channel(channel)}",
            "order": "created_at.desc",
            "limit": str(max(1, min(500, limit))),
            "offset": str(max(0, offset)),
        }
        if genre:
            params["genre"] = f"eq.{genre}"
        if action:
            params["action"] = f"eq.{action}"
        if used is not None:
            params["used"] = f"eq.{'true' if used else 'false'}"
        with httpx.Client(timeout=30.0) as c:
            r = c.get(f"{url}/rest/v1/{_TABLE}", headers=headers, params=params)
            r.raise_for_status()
            rows = r.json()
        return rows if isinstance(rows, list) else []
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-db] 라이브러리 조회 실패: %s", _http_err(e))
        return []


def get_tracks_by_ids(ids: list[str], *, channel: str | None = None) -> list[dict]:
    """id(=audio_id) 목록으로 트랙 조회(영상 만들기용). 빈 입력/오류 시 빈 리스트.

    ID 를 직접 지정하므로 채널 필터는 불필요하다(넘기면 교차채널 방어로 적용).
    반환 행에는 _LIBRARY_SELECT 를 통해 channel 이 포함된다.
    """
    url, key = _supabase_cfg()
    clean = [i for i in (ids or []) if i]
    if not (url and key) or not clean:
        return []
    try:
        headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        params = {"select": _LIBRARY_SELECT, "id": f"in.({','.join(clean)})"}
        if channel:
            params["channel"] = f"eq.{_resolve_channel(channel)}"
        with httpx.Client(timeout=30.0) as c:
            r = c.get(f"{url}/rest/v1/{_TABLE}", headers=headers, params=params)
            r.raise_for_status()
            rows = r.json()
        return rows if isinstance(rows, list) else []
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-db] 트랙 조회 실패(ids=%d): %s", len(clean), _http_err(e))
        return []


def library_stats(*, channel: str | None = None) -> list[dict]:
    """장르별 적립 현황 [{genre, total, unused}]. 단순화를 위해 전체를 읽어 집계한다.

    channel=None → DEFAULT_CHANNEL(where). 통계도 채널별로 갈린다.
    """
    rows = list_library(limit=500, channel=channel)
    agg: dict[str, dict] = {}
    for r in rows:
        g = (r.get("genre") or "").strip()
        if not g:
            continue
        a = agg.setdefault(g, {"genre": g, "total": 0, "unused": 0})
        a["total"] += 1
        if not r.get("used"):
            a["unused"] += 1
    return sorted(agg.values(), key=lambda a: a["total"], reverse=True)


# ── Suno 재활용(#46) — 미사용 트랙 검색 + 사용 마킹 ────────────────────
def find_unused_track(
    genre: str, *, exclude_ids: set[str] | None = None, channel: str | None = None
) -> dict | None:
    """같은 channel·genre 의 미사용(used=false, SUCCESS) 트랙 1개를 최신순으로 반환.

    exclude_ids: 이번 제작 런에서 이미 쓰거나 막 생성한 audio_id 들 — 같은 런 내
    중복(같은 곡 2번 사용)을 막기 위해 제외한다. genre 빈값(레거시)은 호출부에서 차단.
    DB 미설정/오류 시 None(→ 호출부가 Suno 정상 호출 폴백).

    ★ **channel 필터가 이 작업의 핵심이다.** 빠지면 운동용 EDM 이 where;_____ 영상에
      섞여 들어간다(반대도 마찬가지) — 크레딧 낭비가 아니라 잘못된 곡이 업로드되는 사고다.
      channel=None → DEFAULT_CHANNEL(where)로 기존 동작 유지.
    """
    url, key = _supabase_cfg()
    if not (url and key) or not genre:
        return None
    try:
        headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        params = {
            "genre": f"eq.{genre}",
            "used": "eq.false",
            "status": "eq.SUCCESS",
            "channel": f"eq.{_resolve_channel(channel)}",  # ★ 재활용 풀 채널 분리
            "select": "id,theme_slug,task_id,audio_id,title,tags,duration,r2_key,status,used,genre,channel,created_at",
            "order": "created_at.desc",
            "limit": "1",
        }
        ids = [i for i in (exclude_ids or set()) if i]
        if ids:
            params["id"] = f"not.in.({','.join(ids)})"
        with httpx.Client(timeout=30.0) as c:
            r = c.get(f"{url}/rest/v1/{_TABLE}", headers=headers, params=params)
            r.raise_for_status()
            rows = r.json()
        return rows[0] if isinstance(rows, list) and rows else None
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-db] 미사용 트랙 검색 실패(genre=%s): %s", genre, _http_err(e))
        return None


def mark_track_used(audio_id: str) -> bool:
    """트랙을 used=true 로 마킹. 성공 여부 반환(실패해도 호출부는 진행 — 로그만)."""
    url, key = _supabase_cfg()
    if not (url and key) or not audio_id:
        return False
    try:
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=30.0) as c:
            r = c.patch(
                f"{url}/rest/v1/{_TABLE}?id=eq.{audio_id}",
                headers=headers,
                json={"used": True},
            )
            r.raise_for_status()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-db] used 마킹 실패(id=%s): %s", audio_id, _http_err(e))
        return False
