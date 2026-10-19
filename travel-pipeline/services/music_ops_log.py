"""운영 계측 기록(대시보드용, 대표 승인 2026-10-19) — "기록만". 제작·업로드 동작은 바꾸지 않는다.

R2 음악 버킷 music-status/ 아래 JSON 3종:
  - llm_fallback.json        : Claude 장애로 OpenAI 대체가 일어난 마지막 시각·작업·사유 + 월별 횟수.
  - llm_usage_{YYYYMM}.json  : 모델별 입력·출력 토큰과 호출 수(월 누적) — 이번 달 Claude 비용 실측.
  - suno_credits.json        : 날짜(KST)별 Suno 잔액 스냅샷(최근 40일) — 하루 소모량 실측 보정.

쓰기는 프로세스 안에서 모았다가 최대 5분에 1번(FLUSH_SEC) 합쳐서 쓴다(읽고-더해서-쓰기). Railway 는
단일 워커라 경합이 없다. 재시작 때 아직 안 쓴 몇 분치가 빠질 수 있다(대시보드 추정치 용도라 허용).
모든 함수는 예외를 던지지 않는다 — 기록 실패가 가사·검수·업로드를 막으면 안 된다.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
PREFIX = "music-status"
FALLBACK_KEY = f"{PREFIX}/llm_fallback.json"
CREDITS_KEY = f"{PREFIX}/suno_credits.json"
FLUSH_SEC = 300.0
CREDIT_DAYS_KEPT = 40

_LOCK = threading.Lock()
_usage_pending: dict[str, dict[str, dict[str, int]]] = {}   # {YYYYMM: {model: {input, output, calls}}}
_fallback_pending: dict | None = None                         # 마지막 대체 + 월별 증가분
_last_flush = 0.0


def usage_key(month: str) -> str:
    return f"{PREFIX}/llm_usage_{month}.json"


def _month(now: datetime | None = None) -> str:
    return (now or datetime.now(KST)).astimezone(KST).strftime("%Y%m")


def _read(key: str) -> dict:
    try:
        from adapters import r2_storage
        obj = r2_storage._get_client().get_object(Bucket=r2_storage._music_bucket(), Key=key)
        data = json.loads(obj["Body"].read().decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 - 없음·읽기 실패 → 빈 기록
        return {}


def _write(key: str, data: dict) -> bool:
    try:
        from adapters import r2_storage
        r2_storage._get_client().put_object(
            Bucket=r2_storage._music_bucket(), Key=key,
            Body=json.dumps(data, ensure_ascii=False).encode("utf-8"), ContentType="application/json",
        )
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[ops-log] 기록 실패(무시) key=%s: %s", key, str(e)[:160])
        return False


# ── (다) LLM 사용량 ───────────────────────────────────────────────────
def add_usage(model: str | None, input_tokens, output_tokens, *, now: datetime | None = None) -> None:
    """LLM 응답 1건의 토큰 수 누적(Claude·OpenAI 대체 모두 모델 이름으로 구분)."""
    try:
        m = str(model or "unknown")
        with _LOCK:
            cur = _usage_pending.setdefault(_month(now), {}).setdefault(m, {"input": 0, "output": 0, "calls": 0})
            cur["input"] += int(input_tokens or 0)
            cur["output"] += int(output_tokens or 0)
            cur["calls"] += 1
        maybe_flush()
    except Exception as e:  # noqa: BLE001
        logger.debug("[ops-log] 사용량 누적 실패(무시): %s", e)


def add_usage_from(resp, model: str | None) -> None:
    """Anthropic(usage.input_tokens/output_tokens)·OpenAI(usage.prompt_tokens/completion_tokens) 응답 공통."""
    u = getattr(resp, "usage", None)
    if u is None:
        return
    inp = getattr(u, "input_tokens", None)
    out = getattr(u, "output_tokens", None)
    if inp is None and out is None:
        inp, out = getattr(u, "prompt_tokens", 0), getattr(u, "completion_tokens", 0)
    add_usage(model or getattr(resp, "model", None), inp, out)


def read_usage(month: str | None = None) -> dict:
    """그달 모델별 누적(저장분 + 아직 안 쓴 몫)."""
    m = month or _month()
    data = dict((_read(usage_key(m)).get("models") or {}))
    with _LOCK:
        pend = {k: dict(v) for k, v in (_usage_pending.get(m) or {}).items()}
    for model, v in pend.items():
        cur = dict(data.get(model) or {})
        for f in ("input", "output", "calls"):
            cur[f] = int(cur.get(f) or 0) + int(v.get(f) or 0)
        data[model] = cur
    return data


# ── (나) OpenAI 대체 ──────────────────────────────────────────────────
def note_fallback(task: str, model: str, reason: str, *, now: datetime | None = None) -> None:
    """Claude 실패 → OpenAI 대체 1건. 마지막 상황은 바로 보이도록 첫 건은 즉시 기록한다."""
    global _fallback_pending
    try:
        t = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        with _LOCK:
            p = _fallback_pending or {"months": {}}
            p.update(last_at=t.isoformat(), last_task=task, last_model=model, last_reason=str(reason)[:200])
            p["months"][_month(t)] = int(p["months"].get(_month(t)) or 0) + 1
            first = _fallback_pending is None
            _fallback_pending = p
        maybe_flush(force=first)
    except Exception as e:  # noqa: BLE001
        logger.debug("[ops-log] 대체 기록 실패(무시): %s", e)


def read_fallback() -> dict:
    data = _read(FALLBACK_KEY)
    with _LOCK:
        p = dict(_fallback_pending or {})
    if p.get("last_at") and p["last_at"] > str(data.get("last_at") or ""):
        data.update({k: p[k] for k in ("last_at", "last_task", "last_model", "last_reason")})
    return data


# ── 묶어 쓰기 ─────────────────────────────────────────────────────────
def maybe_flush(*, force: bool = False) -> None:
    """마지막 쓰기 후 FLUSH_SEC 가 지났으면(또는 force) 모은 몫을 R2 에 합쳐 쓴다."""
    global _last_flush, _fallback_pending
    if not force and time.monotonic() - _last_flush < FLUSH_SEC:
        return
    with _LOCK:
        usage = {m: {k: dict(v) for k, v in models.items()} for m, models in _usage_pending.items()}
        _usage_pending.clear()
        fb = _fallback_pending
        _fallback_pending = None
        _last_flush = time.monotonic()
    for month, models in usage.items():
        doc = _read(usage_key(month))
        merged = dict(doc.get("models") or {})
        for model, v in models.items():
            cur = dict(merged.get(model) or {})
            for f in ("input", "output", "calls"):
                cur[f] = int(cur.get(f) or 0) + int(v.get(f) or 0)
            merged[model] = cur
        if not _write(usage_key(month), {"month": month, "models": merged,
                                         "updated_at": datetime.now(timezone.utc).isoformat()}):
            _restore_usage(month, models)
    if fb:
        doc = _read(FALLBACK_KEY)
        months = dict(doc.get("months") or {})
        for m, n in (fb.get("months") or {}).items():
            months[m] = int(months.get(m) or 0) + int(n)
        doc.update({k: fb[k] for k in ("last_at", "last_task", "last_model", "last_reason")}, months=months)
        if not _write(FALLBACK_KEY, doc):
            with _LOCK:
                _fallback_pending = _fallback_pending or fb


def _restore_usage(month: str, models: dict) -> None:
    """쓰기 실패분을 다음 쓰기로 넘긴다."""
    with _LOCK:
        box = _usage_pending.setdefault(month, {})
        for model, v in models.items():
            cur = box.setdefault(model, {"input": 0, "output": 0, "calls": 0})
            for f in ("input", "output", "calls"):
                cur[f] += int(v.get(f) or 0)


# ── Suno 잔액 스냅샷 ──────────────────────────────────────────────────
def note_credits(balance: int, *, now: datetime | None = None) -> dict:
    """오늘(KST) 잔액을 하루 1개로 기록(같은 날은 마지막 값). 갱신된 스냅샷 dict 반환."""
    day = (now or datetime.now(KST)).astimezone(KST).date().isoformat()
    data = _read(CREDITS_KEY)
    snaps = dict(data.get("days") or {})
    if snaps.get(day) != balance:
        snaps[day] = int(balance)
        snaps = dict(sorted(snaps.items())[-CREDIT_DAYS_KEPT:])
        _write(CREDITS_KEY, {"days": snaps})
    return snaps


def read_credit_snapshots() -> dict:
    return dict(_read(CREDITS_KEY).get("days") or {})
