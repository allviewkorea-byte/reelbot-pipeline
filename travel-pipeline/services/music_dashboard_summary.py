"""음악 채널 메인 대시보드 요약(대표 승인 2026-10-19) — "한눈에 정상인지". 읽기 전용(보여주기만).

GET /api/music/dashboard/summary?channel= 한 번에 상태등·오늘 회차·숫자 4개·최근 7회차·알림을 돌려준다.
자동 회차 동작(스케줄·제작·업로드)은 건드리지 않는다. 쓰기는 Suno 잔액 하루 스냅샷 1건뿐(music_ops_log).
데이터가 없으면 숫자를 지어내지 않는다 — None("—" / "확인 불가")으로 돌려준다.

회차 상태(0단계 승인 표)
  waiting(대기) · producing(제작 중) · retry(재시도 예정) · stalled(멈춤, 하트비트 10분 끊김) ·
  scheduled(업로드 완료·예약) · published(공개됨) · private(비공개 업로드, 검토 후 공개) ·
  failed(실패) · skipped(건너뜀) · off(가동 꺼짐, 행 없음)
상태등: red > yellow > green. 공개 시각 T 는 claim 메타 start_at + 120분(업로드 때 publish_at 이 덮여서).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
LEAD_MIN = 120
LATE_LIMIT_MIN = 180
STALE_MIN = 10               # 복구 E 와 같은 하트비트 기준
CREDITS_PER_CALL = 12        # Suno 1회(2클립) 크레딧 — 프론트 CREDITS_PER_SONG 과 같은 값
WARN_DAYS = 4                # 🟡 크레딧 N일치 미만
ALERT_WINDOW_H = 48          # 알림·🔴 판단에 보는 최근 시간
FALLBACK_WINDOW_H = 24       # OpenAI 대체 🟡
HISTORY_DAYS = 60            # 연속 일수·최근 7회차에 보는 기간
CACHE_SEC = 300.0            # Suno 잔액·비용 5분 캐시

SUCCESS = ("scheduled", "published", "private")
FINISHED = SUCCESS + ("failed", "skipped")

STATUS_LABEL = {
    "waiting": "대기", "producing": "제작 중", "retry": "재시도 예정", "stalled": "멈춤",
    "scheduled": "업로드 완료", "published": "공개됨", "private": "비공개 업로드",
    "failed": "실패", "skipped": "건너뜀", "off": "가동 꺼짐",
}

FAIL_TEXT = {
    "llm_unavailable": "Claude 사용 불가(잔액·장애) — 가사 생성 실패",
    "image_failed": "배경 이미지 생성·검수 실패",
    "upload_gate": "공개 조건 미충족(썸네일·배경 없음)",
    "upload": "유튜브 업로드 실패",
    "suno": "Suno 곡 생성 실패",
    "render": "렌더 검증 불합격(로고 없음 등)",
    "busy": "다른 제작이 길어져 시작 못 함",
    "skipped": "T+3시간까지 시작하지 못해 건너뜀",
}

LANG_LABEL = {"ko": "한국어", "en": "영어", "inst": "연주"}
STYLE_LABEL = {"street": "거리 스냅", "space": "건축 공간"}
AXIS_LABEL = {"strength": "근력", "cardio": "유산소", "warmup": "워밍업"}

# Claude 단가(USD / 1M 토큰, 입력·출력) — 모델 id 접두사로 맞춘다(날짜 접미사 무시).
CLAUDE_PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
}


def _env_float(key: str, default: float | None) -> float | None:
    raw = (os.getenv(key) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _dt(v) -> datetime | None:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=KST)


def _hm(d: datetime | None) -> str:
    return d.astimezone(KST).strftime("%H:%M") if d else "—"


# ── 회차 1개 판정 ─────────────────────────────────────────────────────
def round_T(row: dict) -> datetime | None:
    """공개 시각 T = start_at + 120분(업로드 때 publish_at 이 유튜브 예약값·None 으로 덮이므로)."""
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    start = _dt(meta.get("start_at"))
    if start:
        return start + timedelta(minutes=LEAD_MIN)
    return _dt(meta.get("publish_at"))


def fail_text(row: dict) -> str:
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    code = meta.get("fail_reason")
    if code in FAIL_TEXT:
        return FAIL_TEXT[code]
    raw = str(row.get("error_message") or meta.get("error") or "").strip()
    if "]" in raw[:60]:                       # "[자동 회차 2 · T ..] 원인" → 원인만
        raw = raw.split("]", 1)[1].strip()
    if "가사" in raw and ("비어" in raw or "실패" in raw):
        return "가사 생성 실패 — " + raw[:50]
    return raw[:60] or "원인 미상"


def classify(row: dict, now: datetime) -> dict:
    """claim 행 → 화면용 회차 dict."""
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    T = round_T(row)
    status = row.get("status")
    view = {
        "key": row.get("job_id"), "slot": meta.get("slot"), "day": meta.get("day"),
        "publish_at": T.astimezone(KST).isoformat() if T else None,
        "youtube_url": meta.get("youtube_url"), "mix_id": meta.get("mix_id") or row.get("mix_id"),
        "genre": meta.get("genre"), "bg_style": meta.get("bg_style"), "bg_axis": meta.get("bg_axis"),
        "reason": None, "retry": None,
    }
    if meta.get("state") == "skipped":
        state = "skipped"
        view["reason"] = fail_text(row)
    elif status == "failed":
        retry_at = _dt(meta.get("retry_at"))
        if retry_at and T and now < T:
            state = "retry"
            n = int(meta.get("retries") or 0)
            view["retry"] = f"{_hm(retry_at)} 재시도 {n}/3"
        else:
            state = "failed"
        view["reason"] = fail_text(row)
    elif status in ("queued", "running"):
        hb = _dt(row.get("updated_at"))
        state = "stalled" if hb and hb < now - timedelta(minutes=STALE_MIN) else "producing"
        if state == "stalled":
            view["reason"] = f"하트비트 끊김(마지막 {_hm(hb)}) — 재시작 복구 대기"
    elif status == "completed":
        if meta.get("privacy") == "public":
            state = "published"
        elif meta.get("publish_at"):
            state = "published" if T and T <= now else "scheduled"
        else:
            state = "private"
    else:
        state = "waiting"
    view["status"] = state
    view["label"] = STATUS_LABEL[state]
    return view


def _day_of(v: dict) -> str | None:
    if v.get("day"):
        return str(v["day"])
    T = _dt(v.get("publish_at"))
    return T.astimezone(KST).date().isoformat() if T else None


# ── 오늘 회차 ─────────────────────────────────────────────────────────
def today_rounds(channel: str, st: dict, views_by_key: dict, now: datetime) -> list[dict]:
    """오늘(KST) 예정 회차(현재 설정) + 오늘 날짜의 실제 행(설정이 바뀐 경우 포함)."""
    from services import music_auto_run as ar
    today = now.astimezone(KST).date()
    out: list[dict] = []
    seen: set[str] = set()
    for r in ar.rounds_for_day(channel, today, st.get("publish_hours") or [6, 18], st.get("daily_cap") or 1):
        seen.add(r["key"])
        v = views_by_key.get(r["key"])
        if v is None:
            if now >= r["publish_at"] + timedelta(minutes=LATE_LIMIT_MIN):
                state = "skipped" if st.get("is_active") else "off"
            else:
                state = "waiting" if st.get("is_active") else "off"
            v = {"key": r["key"], "slot": r["slot"], "day": today.isoformat(),
                 "publish_at": r["publish_at"].isoformat(), "status": state, "label": STATUS_LABEL[state],
                 "youtube_url": None, "mix_id": None, "reason": "기록 없음" if state == "skipped" else None,
                 "retry": None, "genre": None, "bg_style": None, "bg_axis": None,
                 "start_at": r["start_at"].isoformat()}
        out.append(v)
    for k, v in views_by_key.items():
        if k not in seen and _day_of(v) == today.isoformat():
            out.append(v)
    return sorted(out, key=lambda v: v.get("publish_at") or "")


DEAD = ("failed", "skipped")   # 이미 끝나 공개되지 않을 회차 — "다음 공개"에서 뺀다


def next_round(channel: str, st: dict, now: datetime, views_by_key: dict | None = None) -> dict | None:
    """지금 이후 공개될 첫 회차 {publish_at, start_at, tomorrow}. T 가 지났거나, T 전에 이미 최종 실패·
    건너뜀으로 끝난 회차는 건너뛴다(재시도 예정은 아직 살아 있어 포함). 오늘 남은 게 없으면 내일 첫 회차."""
    from services import music_auto_run as ar
    today = now.astimezone(KST).date()
    views_by_key = views_by_key or {}
    for day in (today, today + timedelta(days=1), today + timedelta(days=2)):
        for r in ar.rounds_for_day(channel, day, st.get("publish_hours") or [6, 18], st.get("daily_cap") or 1):
            if r["publish_at"] <= now:
                continue
            if (views_by_key.get(r["key"]) or {}).get("status") in DEAD:
                continue
            return {"publish_at": r["publish_at"].isoformat(), "start_at": r["start_at"].isoformat(),
                    "day_offset": (day - today).days}
    return None


def next_round_line(channel: str, st: dict, now: datetime, views_by_key: dict | None = None) -> str:
    if st.get("known") is False:
        return "채널 상태 확인 불가"
    if not st.get("is_active"):
        return "가동 꺼짐 — 자동 회차가 돌지 않습니다"
    nxt = next_round(channel, st, now, views_by_key)
    if not nxt:
        return "다음 회차 없음"
    when = {0: "", 1: "내일 "}.get(nxt["day_offset"], "모레 ")
    return f"다음 공개 {when}{_hm(_dt(nxt['publish_at']))} (제작 {_hm(_dt(nxt['start_at']))} 시작)"


# ── 연속 일수 · 최근 7회차 ────────────────────────────────────────────
def streak_days(views: list[dict], today: date) -> int:
    """오늘부터 거꾸로 — 회차가 있고 전부 성공한 날 +1, 실패·건너뜀·멈춤이 있으면 끊김.
    회차가 하나도 없는 날(가동 OFF)은 건너뛰고 이어간다. 오늘은 진행 중·남은 회차가 있어도 안 끊는다."""
    by_day: dict[str, list[str]] = {}
    for v in views:
        d = _day_of(v)
        if d:
            by_day.setdefault(d, []).append(v["status"])
    n = 0
    for i in range(HISTORY_DAYS + 1):
        d = (today - timedelta(days=i)).isoformat()
        sts = by_day.get(d)
        if not sts:
            continue
        if any(s in ("failed", "skipped", "stalled") for s in sts):
            break
        if any(s in SUCCESS for s in sts) and all(s in SUCCESS or i == 0 for s in sts):
            n += 1
    return n


def recent7(views: list[dict]) -> list[dict]:
    """끝난 회차 T 기준 최근 7개(오래된 → 최근). ok: True 성공 / False 실패 / None 건너뜀."""
    done = [v for v in views if v["status"] in FINISHED and v.get("publish_at")]
    done.sort(key=lambda v: v["publish_at"], reverse=True)
    out = []
    for v in reversed(done[:7]):
        ok = True if v["status"] in SUCCESS else (None if v["status"] == "skipped" else False)
        T = _dt(v["publish_at"])
        out.append({"key": v["key"], "publish_at": v["publish_at"], "status": v["status"], "ok": ok,
                    "text": f"{T.astimezone(KST).strftime('%m/%d %H시대') if T else ''} {v['label']}"
                            + (f" — {v['reason']}" if v.get("reason") else "")})
    return out


# ── 크레딧 ────────────────────────────────────────────────────────────
def configured_daily_credits(states: dict[str, dict]) -> int:
    """가동 중 채널들의 하루 소모 크레딧(설정값) = Σ 하루 회차 × 곡수 × 12."""
    total = 0
    for st in states.values():
        if st.get("is_active"):
            rounds = min(int(st.get("daily_cap") or 1), len(st.get("publish_hours") or [6, 18]))
            total += rounds * int(st.get("track_count") or 1) * CREDITS_PER_CALL
    return total


def measured_daily_credits(snapshots: dict[str, int]) -> float | None:
    """하루 1개 잔액 스냅샷의 연속 날짜 감소분 평균(최근 7개). 충전(증가)은 뺀다. 3개 미만이면 None."""
    days = sorted(snapshots.items())
    drops = []
    for (d0, b0), (d1, b1) in zip(days, days[1:]):
        if (date.fromisoformat(d1) - date.fromisoformat(d0)).days == 1 and b0 > b1:
            drops.append(b0 - b1)
    drops = drops[-7:]
    return sum(drops) / len(drops) if len(drops) >= 3 else None


def credit_view(balance: int | None, states: dict[str, dict], snapshots: dict[str, int]) -> dict:
    if balance is None:
        return {"balance": None, "daily": None, "days_left": None, "level": "unknown", "basis": None}
    measured = measured_daily_credits(snapshots)
    daily = measured if measured else configured_daily_credits(states)
    one_round = max([int(st.get("track_count") or 1) * CREDITS_PER_CALL
                     for st in states.values() if st.get("is_active")] or [0])
    days_left = round(balance / daily, 1) if daily else None
    if one_round and balance < one_round:
        level = "red"
    elif days_left is not None and days_left < WARN_DAYS:
        level = "yellow"
    else:
        level = "ok"
    return {"balance": balance, "daily": round(daily) if daily else None, "days_left": days_left,
            "level": level, "basis": "measured" if measured else "configured", "one_round": one_round}


_suno_cache: dict = {}
_cost_cache: dict = {}
_cache_lock = threading.Lock()


def fetch_suno_balance(timeout: float = 5.0) -> int | None:
    """sunoapi.org 잔액(5분 캐시). 실패·지연 → None(화면은 "확인 불가")."""
    with _cache_lock:
        if _suno_cache and time.monotonic() - _suno_cache["t"] < CACHE_SEC:
            return _suno_cache["v"]
    key = (os.getenv("SUNOAPI_ORG_KEY") or "").strip()
    val = None
    if key:
        try:
            with httpx.Client(timeout=timeout) as c:
                r = c.get("https://api.sunoapi.org/api/v1/generate/credit",
                          headers={"Authorization": f"Bearer {key}"})
            data = r.json().get("data") if r.status_code < 400 else None
            if isinstance(data, (int, float)):
                val = int(data)
            elif isinstance(data, dict):
                raw = data.get("totalCredits", data.get("credits"))
                val = int(raw) if raw is not None else None
        except Exception as e:  # noqa: BLE001
            logger.warning("[dashboard] Suno 잔액 조회 실패: %s", str(e)[:120])
    with _cache_lock:
        _suno_cache.update(t=time.monotonic(), v=val)
    if val is not None:
        try:
            from services import music_ops_log
            music_ops_log.note_credits(val)
        except Exception:  # noqa: BLE001
            pass
    return val


# ── 비용(이번 달, 두 채널 합계 — Claude 사용량이 채널 구분 없이 쌓이므로) ────────────
def _claude_price(model: str) -> tuple[float, float] | None:
    for prefix, p in CLAUDE_PRICES.items():
        if str(model).startswith(prefix):
            return p
    return None


def cost_view(jobs: list[dict], usage: dict, *, krw: float, lambda_per_video: float | None,
              fixed_monthly: float | None, credit_usd: float) -> dict:
    """jobs: 이번 달 제작(manual_render) 행들. usage: music_ops_log.read_usage() 모델별 토큰."""
    suno_calls = image_usd = 0.0
    videos = 0
    for j in jobs:
        meta = j.get("metadata") if isinstance(j.get("metadata"), dict) else {}
        suno_calls += len(((meta.get("recovery") or {}).get("task_ids")) or [])
        for a in ((meta.get("auto_image") or {}).get("attempts") or []):
            image_usd += float(a.get("est_output_usd") or 0)
        if j.get("status") == "completed":
            videos += 1
    claude_usd = 0.0
    unpriced: list[str] = []
    for model, v in (usage or {}).items():
        p = _claude_price(model)
        if p is None:
            unpriced.append(model)
            continue
        claude_usd += (int(v.get("input") or 0) * p[0] + int(v.get("output") or 0) * p[1]) / 1_000_000
    items = {
        "suno": round(suno_calls * CREDITS_PER_CALL * credit_usd, 2),
        "image": round(image_usd, 2),
        "claude": round(claude_usd, 2),
        "lambda": round(videos * lambda_per_video, 2) if lambda_per_video is not None else None,
        "fixed": round(fixed_monthly, 2) if fixed_monthly is not None else None,
    }
    total = round(sum(v for v in items.values() if v is not None), 2)
    return {"usd": total, "krw": round(total * krw), "krw_per_usd": krw, "items": items,
            "excluded": [k for k, v in items.items() if v is None] + (["openai"] if unpriced else []),
            "unpriced_models": unpriced, "videos": videos, "suno_calls": int(suno_calls), "estimate": True}


def month_cost(now: datetime) -> dict | None:
    """이번 달(KST) 두 채널 제작 작업 + LLM 사용량 → 추정 비용(5분 캐시). 실패 → None."""
    with _cache_lock:
        if _cost_cache and time.monotonic() - _cost_cache["t"] < CACHE_SEC:
            return _cost_cache["v"]
    try:
        from services import music_jobs, music_ops_log
        from services import music_auto_run as ar
        start = now.astimezone(KST).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        jobs: list[dict] = []
        for ch in ar.auto_run_channels():
            jobs += music_jobs.list_by_type_since("manual_render", ch, start.isoformat(), limit=500)
        val = cost_view(
            jobs, music_ops_log.read_usage(start.strftime("%Y%m")),
            krw=_env_float("MUSIC_KRW_PER_USD", 1400.0) or 1400.0,
            lambda_per_video=_env_float("MUSIC_COST_LAMBDA_PER_VIDEO_USD", None),
            fixed_monthly=_env_float("MUSIC_COST_FIXED_MONTHLY_USD", 5.0),
            credit_usd=_env_float("MUSIC_SUNO_CREDIT_USD", 0.005) or 0.005,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[dashboard] 비용 계산 실패: %s", e)
        val = None
    with _cache_lock:
        _cost_cache.update(t=time.monotonic(), v=val)
    return val


# ── 알림 · 상태등 ─────────────────────────────────────────────────────
def alerts_and_light(views: list[dict], today: list[dict], st: dict, credits: dict, fallback: dict,
                     queue_count: int | None, now: datetime) -> tuple[list[dict], str]:
    alerts: list[dict] = []
    seen: set[str] = set()
    window = now - timedelta(hours=ALERT_WINDOW_H)
    # 그 뒤에 성공한 회차가 있으면 지난 실패는 "해결됨"(회색, 🔴 판단에서 제외) — 이미 지나간 사고로
    # 빨간불이 하루 넘게 켜져 새 문제가 묻히지 않게(대표 요청 2026-10-20).
    ok_ts = [_dt(v.get("publish_at")) for v in views + today if v.get("status") in SUCCESS]
    last_ok = max((t for t in ok_ts if t), default=None)
    for v in sorted(views + today, key=lambda x: x.get("publish_at") or ""):
        T = _dt(v.get("publish_at"))
        if not T or v["key"] in seen:
            continue
        seen.add(v["key"])
        when = T.astimezone(KST).strftime("%m/%d %H시대")
        if v["status"] in ("failed", "skipped") and T >= window:
            if last_ok is not None and last_ok > T:
                alerts.append({"level": "resolved",
                               "text": f"지난 실패(해결됨) · {when} 회차 {v['label']} — {v.get('reason') or '원인 미상'}"})
            else:
                alerts.append({"level": "red", "text": f"{when} 회차 {v['label']} — {v.get('reason') or '원인 미상'}"})
        elif v["status"] == "stalled":
            alerts.append({"level": "red", "text": f"{when} 회차 멈춤 — {v.get('reason')}"})
        elif v["status"] == "retry":
            alerts.append({"level": "yellow", "text": f"{when} 회차 {v.get('retry')} — {v.get('reason')}"})
    last_fb = _dt(fallback.get("last_at"))
    if last_fb and last_fb >= now - timedelta(hours=FALLBACK_WINDOW_H):
        alerts.append({"level": "yellow", "text": f"Claude 장애 — OpenAI로 대신 처리 중(잔액·결제 확인) · "
                                                   f"마지막 {_hm(last_fb)} ({fallback.get('last_task') or '-'})"})
    if credits["level"] == "red":
        alerts.append({"level": "red", "text": f"Suno 크레딧 {credits['balance']:,} — 다음 회차분({credits['one_round']}) 미만"})
    elif credits["level"] == "yellow":
        alerts.append({"level": "yellow", "text": f"Suno 크레딧 {credits['balance']:,} — 약 {credits['days_left']}일치(충전 필요)"})
    if st.get("known") is False:
        alerts.append({"level": "yellow", "text": "채널 상태 확인 불가(DB 조회 실패) — 잠시 후 다시 확인"})
    elif not st.get("is_active"):
        alerts.append({"level": "yellow", "text": "가동 꺼짐 — 자동 회차가 돌지 않습니다"})
    elif st.get("mode") != "auto":
        q = f" · 검토 대기 {queue_count}개" if queue_count is not None else ""
        alerts.append({"level": "yellow", "text": f"비공개 모드 — 업로드가 비공개로 쌓이는 중{q}"})
    levels = {a["level"] for a in alerts}
    light = "red" if "red" in levels else ("yellow" if "yellow" in levels else "green")
    return alerts, light


LIGHT_TEXT = {"green": "정상", "yellow": "주의", "red": "문제"}


# ── 조립(IO) ─────────────────────────────────────────────────────────
def build(channel: str, *, now: datetime | None = None) -> dict:
    from services import music_jobs, music_ops_log, music_store, music_uploads
    from services import music_auto_run as ar
    now = (now or datetime.now(timezone.utc)).astimezone(KST)
    states = {ch: ar.get_channel_state(ch) for ch in ar.auto_run_channels()}
    st = states.get(channel) or ar.get_channel_state(channel)
    since = (now - timedelta(days=HISTORY_DAYS)).isoformat()
    rows = music_jobs.list_by_type_since(ar.JOB_TYPE, channel, since, limit=300)
    views = [classify(r, now) for r in rows]
    by_key = {v["key"]: v for v in views}
    today = today_rounds(channel, st, by_key, now)
    for v in today:  # 오늘 회차만 영상 언어(곡 DB) — 최대 하루 회차 수만큼 조회
        v["language"] = None
        if v.get("mix_id"):
            up = music_uploads.get_upload(v["mix_id"]) or {}
            v["language"] = music_store.track_language(up.get("slug") or "")
        v["language_label"] = LANG_LABEL.get(v["language"] or "")
        v["bg_label"] = STYLE_LABEL.get(v.get("bg_style") or "") or AXIS_LABEL.get(v.get("bg_axis") or "")
    queue = music_uploads.list_pending(channel=channel)
    queue_count = len(queue) if isinstance(queue, list) else None
    credits = credit_view(fetch_suno_balance(), states, music_ops_log.read_credit_snapshots())
    fallback = music_ops_log.read_fallback()
    alerts, light = alerts_and_light(views, today, st, credits, fallback, queue_count, now)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return {
        "channel": channel,
        "generated_at": now.isoformat(),
        # next: 화면이 공개 시각을 지나면 그 줄을 지우고 바로 다시 읽게(오래된 "다음 공개" 방지).
        "light": {"color": light, "text": LIGHT_TEXT[light], "line": next_round_line(channel, st, now, by_key),
                  "next": next_round(channel, st, now, by_key) if st.get("is_active") and st.get("known") is not False else None},
        "channel_state": {k: st.get(k) for k in ("is_active", "mode", "daily_cap", "track_count", "publish_hours")},
        "today": today,
        "numbers": {
            "streak_days": streak_days(views, now.date()),
            "month_uploads": music_uploads.count_uploaded_since(channel, month_start.isoformat()),
            "credits": credits,
            "month_cost": month_cost(now),
        },
        "recent7": recent7(views),
        "alerts": alerts,
        "queue_count": queue_count,
        "fallback": {k: fallback.get(k) for k in ("last_at", "last_task", "last_model", "last_reason")},
    }
