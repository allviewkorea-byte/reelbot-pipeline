"""음악 파이프라인 작업 추적(운영 가시성, #36) — DB 영구 기록.

수동 생성·재렌더·cron 제작이 거치는 단계를 Supabase `music_jobs` 테이블에 기록해,
대시보드 파이프라인 시각화와 검토대기 진행 카드가 "지금 무슨 일이 일어나는지"를
페이지 이동·기기 전환에도 일관되게 보여준다. 인메모리 _JOBS(재시작 시 소실)와 병행
하며, 이 테이블이 교차 가시성의 단일 진실이다.

music_store.py 와 동일하게 PostgREST 를 httpx 로 직접 호출(신규 의존성 없음). 모든
함수는 best-effort — Supabase 미설정/오류여도 예외를 던지지 않아 파이프라인을 막지
않는다(테스트 1곡 동작·비용 무변경).

⚠️ docs/music_jobs.sql 의 GRANT 1회 실행 필요.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import httpx

from services.music_store import _http_err, _supabase_cfg

logger = logging.getLogger(__name__)

_TABLE = "music_jobs"


def _now() -> str:
    """UTC ISO 타임스탬프(PostgREST 가 timestamptz 로 파싱). 'now()' 문자열은 무효라 직접 생성."""
    return datetime.now(timezone.utc).isoformat()

# 파이프라인 표준 단계(순서 = 진행 순서). 프론트 파이프라인 노드 매핑의 기준.
STEPS: list[str] = [
    "theme",      # 주제 결정
    "vocal",      # suno 보컬 생성(음원)
    "lyrics",     # 가사 생성
    "video",      # Remotion 렌더
    "mix",        # 합성
    "translate",  # 다국어 번역
    "upload",     # YouTube 업로드(공개 게시 시만)
]
_ACTIVE_STATUSES = ("queued", "running")


def _headers(key: str, *, write: bool = False) -> dict[str, str]:
    h = {"apikey": key, "Authorization": f"Bearer {key}"}
    if write:
        h["Content-Type"] = "application/json"
    return h


def _steps_before(step: str | None) -> list[str]:
    """주어진 단계 직전까지의 표준 단계 목록(steps_completed 용, DB 읽기 없이 결정)."""
    if not step or step not in STEPS:
        return []
    return STEPS[: STEPS.index(step)]


def start_job(
    job_type: str,
    *,
    job_id: str | None = None,
    mix_id: str | None = None,
    metadata: dict | None = None,
) -> str:
    """작업 시작 → DB row 생성(status=queued). job_id 반환(미지정 시 생성).

    실패해도 호출자 흐름을 막지 않도록 항상 job_id 를 반환한다(인메모리 job 과 동일 id 사용 가능).
    """
    jid = job_id or uuid.uuid4().hex
    url, key = _supabase_cfg()
    if not (url and key):
        return jid
    record = {
        "job_id": jid,
        "type": job_type,
        "mix_id": mix_id,
        "status": "queued",
        "step": None,
        "step_progress": 0,
        "steps_completed": [],
        "metadata": metadata or {},
    }
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.post(
                f"{url}/rest/v1/{_TABLE}",
                headers={**_headers(key, write=True), "Prefer": "return=minimal"},
                json=[record],
            )
            r.raise_for_status()
    except Exception as e:  # noqa: BLE001 - 추적 실패는 파이프라인을 막지 않음
        logger.warning("[music-jobs] start 기록 실패(job=%s): %s", jid, _http_err(e))
    return jid


def _patch(job_id: str, patch: dict) -> None:
    url, key = _supabase_cfg()
    if not (url and key):
        return
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.patch(
                f"{url}/rest/v1/{_TABLE}?job_id=eq.{job_id}",
                headers={**_headers(key, write=True), "Prefer": "return=minimal"},
                json={**patch, "updated_at": _now()},
            )
            r.raise_for_status()
    except Exception as e:  # noqa: BLE001 - best-effort
        logger.warning("[music-jobs] update 실패(job=%s): %s", job_id, _http_err(e))


def update_job_step(job_id: str, step: str, progress: int = 0) -> None:
    """단계 진행 기록 → status=running, step, step_progress, steps_completed 갱신."""
    _patch(job_id, {
        "status": "running",
        "step": step,
        "step_progress": max(0, min(100, int(progress or 0))),
        "steps_completed": _steps_before(step),
    })


def complete_job(job_id: str, *, mix_id: str | None = None) -> None:
    """완료 기록 → status=completed, completed_at=now. mix_id 가 생기면 함께 기록."""
    patch = {"status": "completed", "step_progress": 100, "completed_at": _now()}
    if mix_id:
        patch["mix_id"] = mix_id
    _patch(job_id, patch)


def fail_job(job_id: str, error: str) -> None:
    """실패 기록 → status=failed, error_message. completed_at 은 비워 둠(검토대기에 노출)."""
    _patch(job_id, {"status": "failed", "error_message": (error or "")[:500]})


def dismiss_job(job_id: str) -> dict:
    """실패 카드 [닫기] — completed_at 을 채워 active 목록에서 제거(상태는 failed 유지)."""
    url, key = _supabase_cfg()
    if not (url and key):
        return {"ok": False, "error": "supabase 미설정"}
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.patch(
                f"{url}/rest/v1/{_TABLE}?job_id=eq.{job_id}",
                headers={**_headers(key, write=True), "Prefer": "return=minimal"},
                json={"completed_at": _now(), "updated_at": _now()},
            )
            r.raise_for_status()
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": _http_err(e)}


_SELECT = (
    "job_id,type,mix_id,status,step,step_progress,steps_completed,"
    "error_message,metadata,created_at,updated_at,completed_at"
)


def list_active() -> list[dict]:
    """진행 중(queued/running) + 미확인 실패(failed & completed_at 비어 있음) 목록.

    실패 작업도 대표가 [닫기] 하기 전까지는 검토대기 상단에 보이도록 포함한다.
    """
    url, key = _supabase_cfg()
    if not (url and key):
        return []
    try:
        params = {
            "select": _SELECT,
            "or": "(status.in.(queued,running),and(status.eq.failed,completed_at.is.null))",
            "order": "created_at.desc",
        }
        with httpx.Client(timeout=15.0) as c:
            r = c.get(f"{url}/rest/v1/{_TABLE}", headers=_headers(key), params=params)
            r.raise_for_status()
            rows = r.json()
        return rows if isinstance(rows, list) else []
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-jobs] active 조회 실패: %s", _http_err(e))
        return []


def get_job(job_id: str) -> dict | None:
    url, key = _supabase_cfg()
    if not (url and key):
        return None
    try:
        params = {"select": _SELECT, "job_id": f"eq.{job_id}", "limit": "1"}
        with httpx.Client(timeout=15.0) as c:
            r = c.get(f"{url}/rest/v1/{_TABLE}", headers=_headers(key), params=params)
            r.raise_for_status()
            rows = r.json()
        return rows[0] if rows else None
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-jobs] get 조회 실패(job=%s): %s", job_id, _http_err(e))
        return None


def list_history(limit: int = 20) -> list[dict]:
    """최근 완료/실패 작업 — 대시보드 통계용. created_at 내림차순."""
    url, key = _supabase_cfg()
    if not (url and key):
        return []
    limit = max(1, min(100, int(limit or 20)))
    try:
        params = {
            "select": _SELECT,
            "status": "in.(completed,failed)",
            "order": "created_at.desc",
            "limit": str(limit),
        }
        with httpx.Client(timeout=15.0) as c:
            r = c.get(f"{url}/rest/v1/{_TABLE}", headers=_headers(key), params=params)
            r.raise_for_status()
            rows = r.json()
        return rows if isinstance(rows, list) else []
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-jobs] history 조회 실패: %s", _http_err(e))
        return []
