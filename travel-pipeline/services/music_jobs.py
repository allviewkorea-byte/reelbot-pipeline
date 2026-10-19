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
from datetime import datetime, timedelta, timezone

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


def _resolve_channel(channel: str | None) -> str:
    """music_channel.resolve_channel 지연 호출(순환 import 회피). 실패해도 예외 없음."""
    try:
        from services.music_channel import resolve_channel

        return resolve_channel(channel)
    except Exception:  # noqa: BLE001 - 추적은 best-effort, 절대 파이프라인을 막지 않는다
        return "rooftop_music"


def start_job(
    job_type: str,
    *,
    job_id: str | None = None,
    mix_id: str | None = None,
    metadata: dict | None = None,
    channel: str | None = None,
) -> str:
    """작업 시작 → DB row 생성(status=queued). job_id 반환(미지정 시 생성).

    실패해도 호출자 흐름을 막지 않도록 항상 job_id 를 반환한다(인메모리 job 과 동일 id 사용 가능).
    channel=None → DEFAULT_CHANNEL(where). 기존 호출부는 수정 불필요.
    """
    jid = job_id or uuid.uuid4().hex
    url, key = _supabase_cfg()
    if not (url and key):
        return jid
    record = {
        "job_id": jid,
        "type": job_type,
        "mix_id": mix_id,
        "channel": _resolve_channel(channel),
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


def touch(job_id: str) -> None:
    """하트비트(복구 E) — updated_at 만 갱신. 긴 단계(Suno·렌더)에서 1분마다."""
    _patch(job_id, {})


def list_unfinished() -> list[dict]:
    """queued/running + completed_at null 전 채널(재시작 복구 E 판정용). 오류 시 빈 리스트."""
    url, key = _supabase_cfg()
    if not (url and key):
        return []
    try:
        params = {"select": _SELECT, "status": "in.(queued,running)", "completed_at": "is.null",
                  "order": "created_at.asc", "limit": "50"}
        with httpx.Client(timeout=15.0) as c:
            r = c.get(f"{url}/rest/v1/{_TABLE}", headers=_headers(key), params=params)
            r.raise_for_status()
            rows = r.json()
        return rows if isinstance(rows, list) else []
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-jobs] unfinished 조회 실패: %s", _http_err(e))
        return []


def list_recent_with_metadata(limit: int = 50) -> list[dict]:
    """최근 작업(15일, 채널 무관) — 곡 재취득(복구 F)이 metadata.recovery.pending_store 를 찾는다."""
    url, key = _supabase_cfg()
    if not (url and key):
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
    try:
        params = {"select": "job_id,metadata,updated_at", "created_at": f"gte.{since}",
                  "order": "created_at.desc", "limit": str(max(1, min(200, limit)))}
        with httpx.Client(timeout=15.0) as c:
            r = c.get(f"{url}/rest/v1/{_TABLE}", headers=_headers(key), params=params)
            r.raise_for_status()
            rows = r.json()
        return rows if isinstance(rows, list) else []
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-jobs] recent 조회 실패: %s", _http_err(e))
        return []


def list_recent_by_type(job_type: str, channel: str | None, limit: int = 2) -> list[dict]:
    """채널의 최근 작업(유형별, created_at 최신순). where 자동 회차 장르 연속 방지용. 오류 → 빈 리스트."""
    url, key = _supabase_cfg()
    if not (url and key):
        return []
    try:
        params = {"select": "job_id,metadata,created_at", "type": f"eq.{job_type}",
                  "channel": f"eq.{_resolve_channel(channel)}", "metadata->>genre": "not.is.null",
                  "order": "created_at.desc", "limit": str(max(1, min(20, limit)))}
        with httpx.Client(timeout=15.0) as c:
            r = c.get(f"{url}/rest/v1/{_TABLE}", headers=_headers(key), params=params)
            r.raise_for_status()
            rows = r.json()
        return rows if isinstance(rows, list) else []
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-jobs] 최근 작업 조회 실패: %s", _http_err(e))
        return []


def claim_job(job_id: str, job_type: str, *, channel: str | None = None, metadata: dict | None = None) -> bool:
    """회차 선점 — job_id(unique)로 insert. 새로 만들었으면 True, 이미 있으면(409)·오류면 False.

    자동 회차(music_auto_run)의 중복 실행 방지용. start_job 과 달리 결과를 돌려준다.
    오류 시 False(안전 쪽: 중복 제작보다 한 회차 누락이 싸다). completed_at 을 채워 두어
    진행 카드에는 안 뜬다(실제 제작은 manual_render 카드가 보여준다). 실패 시 show_failed 로 연다.
    """
    url, key = _supabase_cfg()
    if not (url and key):
        logger.warning("[music-jobs] claim 불가(supabase 미설정) job=%s", job_id)
        return False
    record = {
        "job_id": job_id, "type": job_type, "channel": _resolve_channel(channel),
        "status": "queued", "step": None, "step_progress": 0, "steps_completed": [],
        "metadata": metadata or {}, "completed_at": _now(), "updated_at": _now(),
    }
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.post(
                f"{url}/rest/v1/{_TABLE}",
                headers={**_headers(key, write=True), "Prefer": "return=minimal"},
                json=[record],
            )
        if r.status_code == 409:
            return False
        r.raise_for_status()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-jobs] claim 실패(job=%s): %s", job_id, _http_err(e))
        return False


def reclaim_job(job_id: str, old_updated_at: str | None) -> bool:
    """끊긴 회차 재선점 — updated_at 이 그대로일 때만 갱신(조건부 PATCH). 성공하면 True."""
    url, key = _supabase_cfg()
    if not (url and key and old_updated_at):
        return False
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.patch(
                f"{url}/rest/v1/{_TABLE}",
                params={"job_id": f"eq.{job_id}", "updated_at": f"eq.{old_updated_at}",
                        "status": "in.(queued,running)"},
                headers={**_headers(key, write=True), "Prefer": "return=representation"},
                json={"updated_at": _now()},
            )
            r.raise_for_status()
            rows = r.json()
        return isinstance(rows, list) and len(rows) == 1
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-jobs] reclaim 실패(job=%s): %s", job_id, _http_err(e))
        return False


def reclaim_failed_job(job_id: str, old_updated_at: str | None, metadata: dict) -> bool:
    """실패한 회차를 재시도용으로 다시 선점 — status=failed·updated_at 그대로일 때만(조건부 PATCH).

    같은 회차 키를 그대로 쓰고, 여러 인스턴스가 동시에 노려도 1곳만 성공한다(중복 실행 0).
    """
    url, key = _supabase_cfg()
    if not (url and key and old_updated_at):
        return False
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.patch(
                f"{url}/rest/v1/{_TABLE}",
                params={"job_id": f"eq.{job_id}", "updated_at": f"eq.{old_updated_at}", "status": "eq.failed"},
                headers={**_headers(key, write=True), "Prefer": "return=representation"},
                json={"status": "queued", "error_message": None, "metadata": metadata, "updated_at": _now()},
            )
            r.raise_for_status()
            rows = r.json()
        return isinstance(rows, list) and len(rows) == 1
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-jobs] 재시도 선점 실패(job=%s): %s", job_id, _http_err(e))
        return False


def show_failed(job_id: str, error: str) -> None:
    """실패 기록 + 진행 카드에 실패로 보이게(completed_at 비움)."""
    _patch(job_id, {"status": "failed", "error_message": (error or "")[:500], "completed_at": None})


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


def merge_metadata(job_id: str, extra: dict) -> None:
    """metadata(jsonb)에 키를 덧붙인다 — 기존 키는 보존. best-effort.

    운동 채널 AI 이미지 검수 결과(합격/불합격 사유)를 남기는 용도(신규 컬럼 없이).
    """
    cur = get_job(job_id) or {}
    meta = cur.get("metadata") if isinstance(cur.get("metadata"), dict) else {}
    _patch(job_id, {"metadata": {**meta, **(extra or {})}})


def dismiss_job(job_id: str) -> dict:
    """카드 [닫기](✕) — completed_at 을 채워 active 목록에서만 제거한다.

    **status 는 바꾸지 않는다.** 버튼이 약속한 "작업 추적만 숨김"이 그대로여야 한다 —
    살아 있는 작업을 status=failed 로 바꾸면 이력에 거짓 실패가 남는다.
    ✕ 는 실패 카드가 아니라 진행 중 카드에 달려 있으므로(MusicJobCard) 대상은
    주로 running/queued 다. list_active 가 completed_at 을 함께 봐야 실제로 사라진다.
    """
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
    "error_message,metadata,channel,created_at,updated_at,completed_at"
)


def list_active(*, channel: str | None = None) -> list[dict]:
    """[닫기] 하지 않은 진행 중(queued/running) + 미확인 실패 목록.

    두 가지 모두 completed_at 이 비어 있어야 한다 — [닫기](dismiss_job)가 completed_at
    을 채우는 것으로 목록에서 빠지기 때문이다. 실패 작업도 대표가 [닫기] 하기 전까지는
    검토대기 상단에 보이도록 포함한다.
    channel=None → DEFAULT_CHANNEL(where). 마이그레이션이 기존 행을 where 로 백필하므로
    지금 시점의 결과 집합은 변하지 않는다.
    """
    url, key = _supabase_cfg()
    if not (url and key):
        return []
    try:
        params = {
            "select": _SELECT,
            "channel": f"eq.{_resolve_channel(channel)}",
            # 첫 가지에 completed_at 조건이 없어서, running/queued 작업은 dismiss_job 이
            # completed_at 을 채워도 계속 매칭돼 목록에 되살아났다(✕ 가 안 먹던 원인).
            # ✕ 는 실패 카드가 아니라 **진행 중 카드**에 달려 있어 이 경로가 실사용이다.
            "or": (
                "(and(status.in.(queued,running),completed_at.is.null),"
                "and(status.eq.failed,completed_at.is.null))"
            ),
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


def list_history(limit: int = 20, *, channel: str | None = None) -> list[dict]:
    """최근 완료/실패 작업 — 대시보드 통계용. created_at 내림차순.

    channel=None → DEFAULT_CHANNEL(where).
    """
    url, key = _supabase_cfg()
    if not (url and key):
        return []
    limit = max(1, min(100, int(limit or 20)))
    try:
        params = {
            "select": _SELECT,
            "status": "in.(completed,failed)",
            "channel": f"eq.{_resolve_channel(channel)}",
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
