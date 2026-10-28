"""매일 점검 리포트 + 유튜브 성과(2026-10-28)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import insta_refs, ops_report, yt_stats  # noqa: E402

NOW = datetime(2026, 10, 29, 0, 30, tzinfo=timezone.utc)   # 09:30 KST


class _Rest:
    def __init__(self, tables):
        self.t = tables
        self.calls = []

    def __call__(self, table, method="GET", *, params=None, json_body=None, prefer=None):
        self.calls.append((table, method, params, json_body))
        rows = self.t.setdefault(table, [])
        if method == "POST":
            keys = (params or {}).get("on_conflict", "").split(",")
            for new in json_body:
                rows[:] = [r for r in rows if any(r.get(k) != new.get(k) for k in keys)] + [new]
            return []
        p = params or {}
        out = list(rows)
        if "date" in p and p["date"].startswith("eq."):
            out = [r for r in out if str(r.get("date")) == p["date"][3:]]
        if p.get("order") == "date.desc":
            out.sort(key=lambda r: str(r.get("date")), reverse=True)
        return out[: int(p.get("limit", 1000))]


@pytest.fixture
def rest(monkeypatch):
    r = _Rest({})
    monkeypatch.setattr(insta_refs, "rest", r)
    monkeypatch.setattr("api.routes.system.system_status",
                        lambda: {"suno": {"status": "warn", "message": "크레딧 80"}, "r2": {"status": "ok"},
                                 "checked_at": "x"})
    return r


class _Resp:
    def __init__(self, code, data):
        self.status_code, self._d = code, data

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Http:
    def __init__(self, retention_code=200):
        self.retention_code = retention_code

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, params=None, headers=None):
        ids = (params.get("id") or params.get("filters", "").replace("video==", "")).split(",")
        if url == yt_stats.DATA_API:
            return _Resp(200, {"items": [{"id": i, "statistics": {"viewCount": "100" if i == "v1" else "40",
                                                                  "likeCount": "3", "commentCount": "1"}} for i in ids]})
        if self.retention_code != 200:
            return _Resp(self.retention_code, {})
        return _Resp(200, {"columnHeaders": [{"name": "video"}, {"name": "views"}, {"name": "averageViewDuration"},
                                             {"name": "averageViewPercentage"}],
                           "rows": [[i, 10, 95.5, 41.2] for i in ids]})


def test_refresh_saves_stats_and_retention(rest):
    rest.t["music_uploads"] = [
        {"channel": "workout_music", "youtube_video_id": "v1", "title_kr": "운동1", "genre": "pop",
         "uploaded_at": (NOW - timedelta(days=5)).isoformat()},
        {"channel": "workout_music", "youtube_video_id": "v2", "title_kr": "운동2", "genre": "pop",
         "uploaded_at": (NOW - timedelta(days=4)).isoformat()},
    ]
    st = yt_stats.refresh(NOW, token_fn=lambda ch: "tok", http=_Http())
    rows = rest.t["yt_video_stats"]
    assert st["channels"]["workout_music"]["retention"] == "ok" and len(rows) == 2
    v1 = next(r for r in rows if r["video_id"] == "v1")
    assert v1["views"] == 100 and v1["avg_view_pct"] == 41.2 and v1["date"] == "2026-10-29"
    yt_stats.refresh(NOW, token_fn=lambda ch: "tok", http=_Http())   # 같은 날 다시 → 덮어씀(멱등)
    assert len(rest.t["yt_video_stats"]) == 2


def test_refresh_without_analytics_scope_keeps_stats(rest):
    rest.t["music_uploads"] = [{"channel": "rooftop_music", "youtube_video_id": "v1",
                                "uploaded_at": (NOW - timedelta(days=2)).isoformat()}]
    st = yt_stats.refresh(NOW, token_fn=lambda ch: "tok", http=_Http(retention_code=403))
    assert "재연결" in st["channels"]["rooftop_music"]["retention"]
    assert rest.t["yt_video_stats"][0]["views"] == 100 and "avg_view_pct" not in rest.t["yt_video_stats"][0]


def test_summarize_rows_gain_top_and_genre():
    today = [{"video_id": "a", "channel": "workout_music", "views": 120, "avg_view_pct": 40, "genre": "pop",
              "title": "A", "uploaded_at": (NOW - timedelta(days=5)).isoformat()},
             {"video_id": "b", "channel": "workout_music", "views": 30, "avg_view_pct": 20, "genre": "pop",
              "title": "B", "uploaded_at": (NOW - timedelta(days=4)).isoformat()}]
    prev = [{"video_id": "a", "views": 100}, {"video_id": "b", "views": 25}]
    s = yt_stats.summarize_rows(today, prev, NOW)["workout_music"]
    assert s["views_gain_1d"] == 25 and s["avg_view_pct"] == 30 and s["top_recent"][0]["title"] == "A"
    assert s["by_genre"] == {"pop": 75}


def test_daily_report_ai_summary_and_latest(rest, monkeypatch):
    rest.t["channel_status"] = [{"channel_id": "workout_music", "is_active": True}]
    rest.t["music_jobs"] = [{"job_id": "j1", "type": "cron", "status": "failed", "error_message": "Suno 타임아웃",
                             "metadata": {"channel": "workout_music"}, "created_at": NOW.isoformat()}]
    monkeypatch.setattr(yt_stats, "refresh", lambda now=None, **k: {})
    seen = {}

    def llm(system, user):
        seen["data"] = json.loads(user)
        return json.dumps({"level": "warn", "headline": "확인 필요 2가지", "issues": [
            {"title": "운동 작업 실패", "cause": "Suno 타임아웃", "suggestion": "재시도"}], "good": ["where 정상"]})
    row = ops_report.run(NOW, llm=llm)
    assert seen["data"]["music_jobs"][0]["error"] == "Suno 타임아웃" and seen["data"]["system"]["suno"]["status"] == "warn"
    assert row["date"] == "2026-10-29" and row["summary"]["level"] == "warn" and row["summary"]["source"] == "ai"
    got = ops_report.latest()
    assert got["summary"]["headline"] == "확인 필요 2가지" and "youtube" in got


def test_rule_summary_when_llm_fails(rest, monkeypatch):
    rest.t["channel_status"] = [{"channel_id": "workout_music", "is_active": True},
                                {"channel_id": "rooftop_music", "is_active": False}]
    monkeypatch.setattr(yt_stats, "refresh", lambda now=None, **k: {})
    row = ops_report.run(NOW, llm=lambda s, u: "not json")
    titles = [i["title"] for i in row["summary"]["issues"]]
    assert row["summary"]["source"] == "rule"
    assert any("suno" in t for t in titles) and any("24시간 업로드 없음" in t for t in titles)
    assert not any("where" in t for t in titles)                       # 중단된 채널은 문제 아님


def test_analytics_scope_only_in_music_auth():
    from services import music_youtube_oauth as mo, youtube_oauth as yo
    assert mo.ANALYTICS_SCOPE in mo.AUTH_SCOPES and mo.ANALYTICS_SCOPE not in yo.SCOPES
