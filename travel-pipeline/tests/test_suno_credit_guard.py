"""Suno 크레딧 부족 미리 경고 + 충전 시 당일 회차 복구 (대표 2026-11-16)."""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import music_auto_run as ar  # noqa: E402
from services import music_dashboard_summary as mds  # noqa: E402
from services import music_twins as tw  # noqa: E402
from services import ops_report  # noqa: E402


def _round(hours_to_T: float, now: datetime) -> dict:
    T = now + timedelta(hours=hours_to_T)
    return {"channel": "workout_music", "slot": 1, "key": "k", "publish_at": T, "start_at": T - timedelta(minutes=120)}


def test_precheck_raises_early_credit_failure(monkeypatch):
    monkeypatch.setattr(mds, "fetch_suno_balance", lambda: 5)
    monkeypatch.setattr(tw, "pick", lambda ch, **k: None)
    from services import music_manual
    monkeypatch.setattr(music_manual, "start", lambda *a, **k: pytest.fail("크레딧 부족이면 제작 시작 금지"))
    r = ar.rounds_for_day("workout_music", date.today() + timedelta(days=1), [6, 18], 1)[0]
    with pytest.raises(ar.RoundFailed) as e:
        ar._produce(r, {"track_count": 1}, sleep=lambda s: None)
    assert e.value.reason == ar.CREDIT_REASON and e.value.early


def test_twin_day_needs_no_credits(monkeypatch):
    from services import music_jobs, music_manual
    monkeypatch.setattr(mds, "fetch_suno_balance", lambda: 0)
    monkeypatch.setattr(music_jobs, "merge_metadata", lambda *a, **k: None)
    monkeypatch.setattr(tw, "pick", lambda ch, **k: {"audio_id": "b", "tag_combo": {"action": "workout"}, "language": "inst"})

    def _start(*a, **k):
        music_manual._JOBS["jc"] = {"status": "done", "mix_id": "m", "video_url": "https://x", "frame_thumb_key": "f"}
        return {"ok": True, "job_id": "jc"}
    monkeypatch.setattr(music_manual, "start", _start)
    monkeypatch.setattr(music_manual, "run", lambda jid: None)
    r = ar.rounds_for_day("workout_music", date.today() + timedelta(days=1), [6, 18], 1)[0]
    assert ar._produce(r, {"track_count": 1}, sleep=lambda s: None) == "m"


def test_balance_unknown_does_not_block(monkeypatch):
    monkeypatch.setattr(mds, "fetch_suno_balance", lambda: None)
    ar._check_suno_credits({"key": "k"}, {"track_count": 1})       # 예외 없음


def test_credit_failure_retries_beyond_three_until_T():
    now = datetime(2026, 11, 16, 10, 0, tzinfo=ar.KST)
    r = _round(1.5, now)
    assert ar.next_retry_at(r, ar.MAX_RETRIES, True, now) is None                       # 일반 실패는 3회까지
    assert ar.next_retry_at(r, ar.MAX_RETRIES + 5, True, now, ar.CREDIT_REASON) is not None
    assert ar.next_retry_at(_round(0.2, now), 9, True, now, ar.CREDIT_REASON) is None    # T 임박이면 끝


def test_daily_report_credit_issue_on_top():
    base = {"level": "ok", "headline": "이상 없음", "issues": [], "good": []}
    red = {"suno_credits": {"level": "red", "balance": 5, "one_round": 12}}
    out = ops_report.apply_credit_issue(base, red)
    assert out["level"] == "error" and "크레딧 부족" in out["issues"][0]["title"] and "크레딧" in out["headline"]
    yellow = {"suno_credits": {"level": "yellow", "balance": 30, "days_left": 2.5, "daily": 12}}
    s2 = {"level": "warn", "headline": "확인 필요 1가지",
          "issues": [{"title": "업로드 없음"}, {"title": "Suno 크레딧 적음"}], "good": []}
    out2 = ops_report.apply_credit_issue(s2, yellow)
    assert out2["level"] == "warn" and [i["title"][:8] for i in out2["issues"]][0].startswith("Suno 크레딧")
    assert len(out2["issues"]) == 2 and out2["headline"] == "확인 필요 1가지"            # 중복 제거
    assert ops_report.apply_credit_issue(base, {"suno_credits": {"level": "ok"}}) == base
