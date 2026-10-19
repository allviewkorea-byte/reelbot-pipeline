"""메인 대시보드 요약(PR A) — 회차 판정·상태등·알림·연속 일수·최근 7회차·크레딧·비용·기록 3건.

외부 호출(Supabase·R2·Suno·Claude·OpenAI) 없이 전부 모킹.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import music_dashboard_summary as ds  # noqa: E402
from services import music_ops_log as ops  # noqa: E402
from test_workout_image_reuse import _FakeS3  # noqa: E402

KST = ds.KST
NOW = datetime(2026, 10, 19, 17, 0, tzinfo=KST)
WORKOUT = "workout_music"


def _row(T: datetime, status: str, *, updated: datetime | None = None, error: str | None = None, **meta) -> dict:
    start = T - timedelta(minutes=120)
    return {"job_id": f"auto-{WORKOUT}-{T:%Y%m%d}-{meta.pop('slot', 1)}", "status": status,
            "updated_at": (updated or T).isoformat(), "error_message": error,
            "metadata": {"day": T.date().isoformat(), "start_at": start.isoformat(), **meta}}


# ── 회차 판정 ─────────────────────────────────────────────────────────
def test_classify_success_variants():
    T = NOW - timedelta(hours=3)
    pub = ds.classify(_row(T, "completed", privacy="public", publish_at=None, youtube_url="https://y/1"), NOW)
    assert pub["status"] == "published" and pub["youtube_url"] == "https://y/1"
    assert pub["publish_at"] == T.isoformat()                        # publish_at 이 None 이어도 T = start+120
    sched = ds.classify(_row(NOW + timedelta(hours=1), "completed", privacy="private",
                             publish_at="2026-10-19T09:00:00.000Z"), NOW)
    assert sched["status"] == "scheduled" and sched["label"] == "업로드 완료"
    passed = ds.classify(_row(T, "completed", privacy="private", publish_at="2026-10-19T05:00:00.000Z"), NOW)
    assert passed["status"] == "published"                            # 예약 시각 지남
    semi = ds.classify(_row(T, "completed", privacy="private", publish_at=None), NOW)
    assert semi["status"] == "private" and semi["label"] == "비공개 업로드"


def test_classify_failures_retry_stall_skip():
    T = NOW + timedelta(minutes=90)
    f = ds.classify(_row(NOW - timedelta(hours=5), "failed", fail_reason="llm_unavailable"), NOW)
    assert f["status"] == "failed" and f["reason"] == "Claude 사용 불가(잔액·장애) — 가사 생성 실패"
    old = ds.classify(_row(NOW - timedelta(days=1), "failed",
                           error="[자동 회차 2 · T 10-18 18:19] 제작 실패: 가사 플랜 생성 결과가 비어 있습니다(전 배치 실패)."), NOW)
    assert old["reason"].startswith("제작 실패") or "가사" in old["reason"]       # #343 이전 행 — 원문 사유
    r = ds.classify(_row(T, "failed", fail_reason="llm_unavailable", retry_at=(NOW + timedelta(minutes=10)).isoformat(),
                         retries=2), NOW)
    assert r["status"] == "retry" and r["retry"] == "17:10 재시도 2/3"
    st = ds.classify(_row(T, "running", updated=NOW - timedelta(minutes=11), state="producing"), NOW)
    assert st["status"] == "stalled" and "하트비트" in st["reason"]
    live = ds.classify(_row(T, "running", updated=NOW - timedelta(minutes=2)), NOW)
    assert live["status"] == "producing"
    sk = ds.classify(_row(NOW - timedelta(hours=4), "failed", state="skipped", fail_reason="skipped"), NOW)
    assert sk["status"] == "skipped" and "건너뜀" in sk["reason"]


# ── 상태등 · 알림 ─────────────────────────────────────────────────────
ACTIVE = {"is_active": True, "mode": "auto", "daily_cap": 2, "track_count": 10, "publish_hours": [6, 18]}
OK_CREDITS = {"level": "ok", "balance": 6310, "days_left": 13.1, "one_round": 120}


def _light(views, st=ACTIVE, credits=OK_CREDITS, fallback=None, queue=0):
    return ds.alerts_and_light(views, [], st, credits, fallback or {}, queue, NOW)


def test_light_cases():
    ok = ds.classify(_row(NOW - timedelta(hours=3), "completed", privacy="public"), NOW)
    assert _light([ok]) == ([], "green")
    fail = ds.classify(_row(NOW - timedelta(hours=10), "failed", fail_reason="render"), NOW)
    alerts, light = _light([ok, fail])
    assert light == "red" and "렌더 검증 불합격" in alerts[0]["text"] and "10/19 07시대" in alerts[0]["text"]
    old_fail = ds.classify(_row(NOW - timedelta(days=3), "failed", fail_reason="render"), NOW)
    assert _light([old_fail])[1] == "green"                                       # 48시간 지난 실패는 알림 없음
    skip = ds.classify(_row(NOW - timedelta(hours=4), "failed", state="skipped", fail_reason="skipped"), NOW)
    assert _light([skip])[1] == "red"
    stall = ds.classify(_row(NOW + timedelta(hours=1), "running", updated=NOW - timedelta(minutes=30)), NOW)
    assert _light([stall])[1] == "red"
    upload = ds.classify(_row(NOW - timedelta(hours=2), "failed", fail_reason="upload"), NOW)
    assert "유튜브 업로드 실패" in _light([upload])[0][0]["text"]


def test_light_yellow_cases():
    assert _light([], st={**ACTIVE, "is_active": False})[1] == "yellow"
    alerts, light = _light([], st={**ACTIVE, "mode": "semi"}, queue=4)
    assert light == "yellow" and "검토 대기 4개" in alerts[0]["text"]
    fb = {"last_at": (NOW - timedelta(hours=2)).isoformat(), "last_task": "lyrics_write"}
    alerts, light = _light([], fallback=fb)
    assert light == "yellow" and "OpenAI로 대신 처리 중" in alerts[0]["text"] and "lyrics_write" in alerts[0]["text"]
    assert _light([], fallback={"last_at": (NOW - timedelta(hours=30)).isoformat()})[1] == "green"
    assert _light([], credits={**OK_CREDITS, "level": "yellow", "days_left": 3.2})[1] == "yellow"
    assert _light([], credits={**OK_CREDITS, "level": "red", "balance": 100})[1] == "red"
    retry = ds.classify(_row(NOW + timedelta(minutes=90), "failed", fail_reason="suno",
                             retry_at=(NOW + timedelta(minutes=5)).isoformat(), retries=1), NOW)
    assert _light([retry])[1] == "yellow"


# ── 연속 일수 · 최근 7회차 ────────────────────────────────────────────
def _day(d: int, *statuses):
    out = []
    for i, s in enumerate(statuses, 1):
        T = datetime(2026, 10, d, 6 + 12 * (i - 1), 30, tzinfo=KST)
        out.append({"key": f"k{d}-{i}", "day": f"2026-10-{d:02d}", "publish_at": T.isoformat(), "status": s,
                    "label": ds.STATUS_LABEL[s], "reason": "사유" if s in ("failed", "skipped") else None})
    return out


def test_streak_rules():
    views = (_day(12, "published", "published") + _day(13, "failed") + _day(14, "published")
             + _day(16, "published", "published") + _day(17, "published")       # 15일: OFF(행 없음) → 건너뜀
             + _day(18, "published", "private") + _day(19, "published", "producing"))   # 오늘 진행 중은 안 끊김
    assert ds.streak_days(views, date(2026, 10, 19)) == 5                          # 19·18·17·16·14, 13 실패에서 끊김
    assert ds.streak_days(_day(19, "skipped"), date(2026, 10, 19)) == 0
    assert ds.streak_days(_day(19, "producing") + _day(18, "published"), date(2026, 10, 19)) == 1
    assert ds.streak_days(_day(18, "published") + _day(17, "published", "published"), date(2026, 10, 19)) == 2  # cap 변경


def test_recent7_order_and_colors():
    views = _day(16, "published") + _day(17, "failed", "published") + _day(18, "skipped", "private") \
        + _day(19, "published", "producing")
    r = ds.recent7(views)
    assert len(r) == 6 and [x["ok"] for x in r] == [True, False, True, None, True, True]
    assert r[1]["text"].startswith("10/17 06시대 실패 — 사유")
    many = sum((_day(d, "published", "published") for d in range(10, 19)), [])
    assert len(ds.recent7(many)) == 7 and ds.recent7(many)[-1]["key"] == "k18-2"


# ── 크레딧 ────────────────────────────────────────────────────────────
STATES = {WORKOUT: ACTIVE, "rooftop_music": {**ACTIVE, "publish_hours": [8, 21]}}


def test_credit_configured_and_measured():
    assert ds.configured_daily_credits(STATES) == 480
    c = ds.credit_view(6310, STATES, {})
    assert c["days_left"] == 13.1 and c["basis"] == "configured" and c["level"] == "ok"
    assert ds.credit_view(1800, STATES, {})["level"] == "yellow"                   # 4일치(1,920) 미만
    assert ds.credit_view(100, STATES, {})["level"] == "red"                       # 1회차분(120) 미만
    snaps = {"2026-10-14": 9000, "2026-10-15": 8700, "2026-10-16": 8400, "2026-10-17": 12000,
             "2026-10-18": 11700, "2026-10-19": 11400}
    assert ds.measured_daily_credits(snaps) == 300                                 # 충전(증가)은 제외
    c = ds.credit_view(11400, STATES, snaps)
    assert c["basis"] == "measured" and c["daily"] == 300 and c["days_left"] == 38.0
    assert ds.credit_view(None, STATES, {})["level"] == "unknown"
    assert ds.credit_view(6310, {WORKOUT: {**ACTIVE, "is_active": False}}, {})["days_left"] is None


@pytest.mark.parametrize("exc", [httpx.ConnectTimeout("t"), httpx.ReadTimeout("t"), RuntimeError("x")])
def test_suno_balance_failure_is_none_and_cached(monkeypatch, exc):
    monkeypatch.setenv("SUNOAPI_ORG_KEY", "k")
    monkeypatch.setattr(ds, "_suno_cache", {})
    calls = []

    class _C:
        def __init__(self, timeout):
            calls.append(timeout)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            raise exc
    monkeypatch.setattr(ds.httpx, "Client", _C)
    assert ds.fetch_suno_balance() is None and ds.fetch_suno_balance() is None
    assert calls == [5.0]                                                          # 5초 타임아웃·5분 캐시


def test_suno_balance_ok_records_snapshot(monkeypatch):
    monkeypatch.setenv("SUNOAPI_ORG_KEY", "k")
    monkeypatch.setattr(ds, "_suno_cache", {})
    noted = []
    monkeypatch.setattr(ops, "note_credits", lambda v: noted.append(v))

    class _C:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            return SimpleNamespace(status_code=200, json=lambda: {"code": 200, "data": 6310})
    monkeypatch.setattr(ds.httpx, "Client", _C)
    assert ds.fetch_suno_balance() == 6310 and noted == [6310]


# ── 비용 ─────────────────────────────────────────────────────────────
def test_cost_view():
    jobs = [{"status": "completed", "metadata": {"recovery": {"task_ids": ["t"] * 10},
                                                 "auto_image": {"attempts": [{"est_output_usd": 0.0424}] * 3}}},
            {"status": "failed", "metadata": {"recovery": {"task_ids": []}}}]
    usage = {"claude-haiku-4-5-20251001": {"input": 1_000_000, "output": 200_000},
             "claude-sonnet-4-6": {"input": 100_000, "output": 10_000}, "gpt-4o": {"input": 5000, "output": 900}}
    c = ds.cost_view(jobs, usage, krw=1400, lambda_per_video=None, fixed_monthly=5, credit_usd=0.005)
    assert c["items"] == {"suno": 0.6, "image": 0.13, "claude": 2.45, "lambda": None, "fixed": 5.0}
    assert c["usd"] == 8.18 and c["krw"] == 11452 and set(c["excluded"]) == {"lambda", "openai"}
    c2 = ds.cost_view(jobs, {}, krw=1400, lambda_per_video=0.8, fixed_monthly=5, credit_usd=0.005)
    assert c2["items"]["lambda"] == 0.8 and c2["excluded"] == []


# ── 조립(IO 모킹) ─────────────────────────────────────────────────────
def test_build_survives_suno_failure(monkeypatch):
    from services import music_auto_run as ar
    from services import music_jobs, music_store, music_uploads
    monkeypatch.setattr(ar, "get_channel_state", lambda ch: dict(ACTIVE))
    T1 = datetime(2026, 10, 19, 6, 28, tzinfo=KST)
    rows = [_row(T1, "completed", privacy="private", publish_at="2026-10-18T21:28:00.000Z",
                 youtube_url="https://y/a", mix_id="m1", bg_axis="cardio")]
    monkeypatch.setattr(music_jobs, "list_by_type_since", lambda *a, **k: rows if a[0] == "auto_run" else [])
    monkeypatch.setattr(music_uploads, "get_upload", lambda mix: {"slug": "s1"})
    monkeypatch.setattr(music_store, "track_language", lambda slug: "en")
    monkeypatch.setattr(music_uploads, "list_pending", lambda channel=None: [])
    monkeypatch.setattr(music_uploads, "count_uploaded_since", lambda ch, since: 36)
    monkeypatch.setattr(ds, "fetch_suno_balance", lambda: None)
    monkeypatch.setattr(ops, "read_credit_snapshots", lambda: {})
    monkeypatch.setattr(ops, "read_fallback", lambda: {})
    monkeypatch.setattr(ops, "read_usage", lambda month=None: {})
    monkeypatch.setattr(ds, "_cost_cache", {})
    out = ds.build(WORKOUT, now=NOW)
    assert out["numbers"]["credits"]["balance"] is None and out["numbers"]["credits"]["level"] == "unknown"
    assert out["numbers"]["month_uploads"] == 36 and out["numbers"]["streak_days"] == 1
    t = out["today"]
    assert len(t) == 2 and t[0]["status"] == "published" and t[0]["language_label"] == "영어"
    assert t[0]["bg_label"] == "유산소" and t[1]["status"] == "waiting"
    assert out["light"]["color"] == "green" and out["light"]["line"].startswith("다음 공개 18:")
    assert out["numbers"]["month_cost"]["items"]["fixed"] == 5.0


def test_today_unrecorded_past_round():
    st = {**ACTIVE}
    late = datetime(2026, 10, 19, 23, 0, tzinfo=KST)
    today = ds.today_rounds(WORKOUT, st, {}, late)
    assert [v["status"] for v in today] == ["skipped", "skipped"]                 # 둘 다 T+3시간 지남·행 없음
    assert all(v["reason"] == "기록 없음" for v in today)
    mid = ds.today_rounds(WORKOUT, st, {}, NOW)                                   # 17:00 — 1회차 지남, 2회차 대기
    assert [v["status"] for v in mid] == ["skipped", "waiting"]
    off = ds.today_rounds(WORKOUT, {**st, "is_active": False}, {}, late)
    assert {v["status"] for v in off} == {"off"}


# ── 기록 (가) 건너뛴 회차 ─────────────────────────────────────────────
@pytest.fixture
def tick_env(monkeypatch):
    from services import music_auto_run as ar
    from services import music_jobs
    recorded = []
    monkeypatch.setattr(music_jobs, "get_job", lambda key: None)
    monkeypatch.setattr(music_jobs, "record_skipped", lambda key, t, **k: recorded.append((key, k)) or True)
    monkeypatch.setattr(ar, "_LOGGED_SKIP", set())
    monkeypatch.setattr(ar, "_try_launch", lambda *a: False)
    monkeypatch.setattr(ar, "auto_run_channels", lambda: [WORKOUT])
    monkeypatch.delenv("MUSIC_AUTO_RUN", raising=False)
    return ar, recorded


def test_skip_recorded_once(tick_env, monkeypatch):
    ar, recorded = tick_env
    monkeypatch.setattr(ar, "get_channel_state", lambda ch: {**ACTIVE, "updated_at": "2026-10-01T00:00:00+00:00"})
    late = datetime(2026, 10, 19, 23, 50, tzinfo=KST)
    ar.tick(late)
    ar.tick(late)
    keys = [k for k, _ in recorded]
    assert len(keys) == len(set(keys)) == 2 and all(k.startswith("auto-workout_music-20261019") for k in keys)
    meta = recorded[0][1]["metadata"]
    assert meta["state"] == "skipped" and meta["fail_reason"] == "skipped" and recorded[0][1]["channel"] == WORKOUT


def test_skip_not_recorded_when_turned_on_after_T(tick_env, monkeypatch):
    ar, recorded = tick_env
    monkeypatch.setattr(ar, "get_channel_state",
                        lambda ch: {**ACTIVE, "updated_at": "2026-10-19T14:00:00+00:00"})   # KST 23:00 에 켬
    ar.tick(datetime(2026, 10, 19, 23, 50, tzinfo=KST))
    assert recorded == []


# ── 기록 (나)(다) R2 JSON ─────────────────────────────────────────────
@pytest.fixture
def s3(monkeypatch):
    from adapters import r2_storage
    fake = _FakeS3()
    monkeypatch.setattr(r2_storage, "_get_client", lambda: fake)
    monkeypatch.setattr(ops, "_usage_pending", {})
    monkeypatch.setattr(ops, "_fallback_pending", None)
    monkeypatch.setattr(ops, "_last_flush", -ops.FLUSH_SEC)  # 부팅 직후(monotonic < 5분)에도 첫 쓰기가 바로 되게
    return fake


def test_usage_accumulates_and_merges(s3, monkeypatch):
    import json
    ops.add_usage("claude-haiku-4-5", 100, 20, now=NOW)                 # 첫 건 → 바로 쓰기
    ops.add_usage("claude-haiku-4-5", 50, 5, now=NOW)                   # 5분 안 → 모아 둠
    saved = json.loads(s3.objs[ops.usage_key("202610")][0])["models"]["claude-haiku-4-5"]
    assert saved == {"input": 100, "output": 20, "calls": 1}
    assert ops.read_usage("202610")["claude-haiku-4-5"] == {"input": 150, "output": 25, "calls": 2}
    ops.maybe_flush(force=True)
    saved = json.loads(s3.objs[ops.usage_key("202610")][0])["models"]["claude-haiku-4-5"]
    assert saved == {"input": 150, "output": 25, "calls": 2}


def test_fallback_recorded_immediately(s3):
    import json
    ops.note_fallback("lyrics_write", "gpt-4o", "BadRequestError(400): credit", now=NOW)
    doc = json.loads(s3.objs[ops.FALLBACK_KEY][0])
    assert doc["last_task"] == "lyrics_write" and doc["months"]["202610"] == 1
    ops.note_fallback("lyrics_plan", "gpt-4o-mini", "x", now=NOW + timedelta(minutes=1))
    assert ops.read_fallback()["last_task"] == "lyrics_plan"                 # 아직 안 쓴 몫도 보인다


def test_credit_snapshot_daily(s3):
    ops.note_credits(6310, now=NOW)
    ops.note_credits(6190, now=NOW + timedelta(hours=1))
    ops.note_credits(5900, now=NOW + timedelta(days=1))
    assert ops.read_credit_snapshots() == {"2026-10-19": 6190, "2026-10-20": 5900}


def test_r2_failure_never_raises(monkeypatch):
    from adapters import r2_storage
    monkeypatch.setattr(r2_storage, "_get_client", lambda: (_ for _ in ()).throw(RuntimeError("r2 down")))
    monkeypatch.setattr(ops, "_last_flush", -ops.FLUSH_SEC)  # 부팅 직후(monotonic < 5분)에도 첫 쓰기가 바로 되게
    ops.add_usage("m", 1, 1)
    ops.note_fallback("t", "m", "r")
    assert ops.read_fallback()["last_task"] == "t" and ops.note_credits(1) == {"%s" % datetime.now(KST).date(): 1}


def test_llm_paths_record_usage_and_fallback(monkeypatch):
    from services import music_llm_fallback as fb
    from services import music_lyrics
    usage, notes = [], []
    monkeypatch.setattr(ops, "add_usage_from", lambda resp, model: usage.append(model))
    monkeypatch.setattr(ops, "note_fallback", lambda task, model, reason: notes.append((task, model)))
    ok = SimpleNamespace(content=[SimpleNamespace(text="hi")], usage=SimpleNamespace(input_tokens=3, output_tokens=4))
    claude = SimpleNamespace(messages=SimpleNamespace(create=lambda **k: ok))
    monkeypatch.setattr(music_lyrics, "_client", lambda: claude)
    assert music_lyrics._call("s", "u", model="claude-haiku-4-5") == "hi" and usage == ["claude-haiku-4-5"]
    import anthropic
    req = httpx.Request("POST", "https://api.anthropic.com")
    bad = SimpleNamespace(messages=SimpleNamespace(create=lambda **k: (_ for _ in ()).throw(
        anthropic.BadRequestError("credit", response=httpx.Response(400, request=req), body=None))))
    monkeypatch.setattr(music_lyrics, "_client", lambda: bad)
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.delenv("MUSIC_LLM_FALLBACK", raising=False)
    oa = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **k: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))], usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2)))))
    monkeypatch.setattr(fb, "_client", lambda: oa)
    assert music_lyrics._call("s", "u", task="lyrics_write", strong=True) == "ok"
    assert notes == [("lyrics_write", "gpt-4o")] and usage[-1] == "gpt-4o"


def test_add_usage_from_shapes(monkeypatch):
    got = []
    monkeypatch.setattr(ops, "add_usage", lambda m, i, o: got.append((m, i, o)))
    ops.add_usage_from(SimpleNamespace(usage=SimpleNamespace(input_tokens=5, output_tokens=6)), "claude-x")
    ops.add_usage_from(SimpleNamespace(usage=SimpleNamespace(prompt_tokens=7, completion_tokens=8)), "gpt-4o")
    ops.add_usage_from(SimpleNamespace(usage=None), "z")
    assert got == [("claude-x", 5, 6), ("gpt-4o", 7, 8)]


def test_route_registered():
    from api.routes import music
    assert any(getattr(r, "path", "") == "/dashboard/summary" for r in music.router.routes)
    _ = timezone.utc


def test_unknown_channel_state_is_not_off():
    alerts, light = ds.alerts_and_light([], [], {**ACTIVE, "is_active": False, "known": False}, OK_CREDITS, {}, 0, NOW)
    assert light == "yellow" and "확인 불가" in alerts[0]["text"] and "가동 꺼짐" not in alerts[0]["text"]
    assert ds.next_round_line(WORKOUT, {"known": False}, NOW) == "채널 상태 확인 불가"
