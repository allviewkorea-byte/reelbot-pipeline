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

import httpx

from services.music_store import _http_err, _supabase_cfg

logger = logging.getLogger(__name__)

_TABLE = "music_uploads"
_SELECT = (
    "slug,mix_id,title_kr,genre,mood,mp4_url,gpt_prompt,thumbnail_r2_key,viz_spec,"
    "status,youtube_video_id,youtube_url,created_at"
)


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
    gpt_prompt: str = "",
    thumbnail_r2_key: str | None = None,
    viz_spec: dict | None = None,
) -> dict:
    """영상 생성 완료 → 검토 대기(pending) 행 upsert(mix_id 기준). {stored, error}.

    thumbnail_r2_key: 첫프레임 자동 썸네일(#20) 키. 주면 공개 업로드 게이트가 자동 충족.
    viz_spec: 곡 분석 결과(#20) 캐시 — 같은 mix 재렌더 시 재사용.
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
    if thumbnail_r2_key:
        record["thumbnail_r2_key"] = thumbnail_r2_key
    if viz_spec is not None:
        record["viz_spec"] = viz_spec
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


def list_pending() -> list[dict]:
    """검토 대기(status=pending) 목록 최신순. 미설정/오류 시 빈 리스트."""
    url, key = _supabase_cfg()
    if not (url and key):
        return []
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.get(
                f"{url}/rest/v1/{_TABLE}",
                headers=_headers(key),
                params={"status": "eq.pending", "select": _SELECT, "order": "created_at.desc"},
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


def list_uploaded(limit: int = 12) -> list[dict]:
    """공개 업로드 완료(status=uploaded) 목록 최신순 — 대시보드 '최근 업로드' 마퀴용."""
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
                    "order": "created_at.desc", "limit": str(limit),
                },
            )
            r.raise_for_status()
            rows = r.json()
        return rows if isinstance(rows, list) else []
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-uploads] 업로드 목록 조회 실패: %s", _http_err(e))
        return []


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
