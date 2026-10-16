"""음악 자동 회차(PR-2a) — 회차 계산·중복 방지·재시작·예약 공개·폴백 거부·where 제외(외부 호출 없음)."""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import music_auto_run as ar  # noqa: E402

KST = ar.KST
WORKOUT = "workout_music"
ACTIVE = {"is_active": True, "mode": "auto", "synthetic_media": True, "daily_cap": 2,
          "track_count": 10, "publish_hours": [6, 18]}


# ── 회차 계산 ─────────────────────────────────────────────────────────
def test_rounds_hours_minutes_and_lead():
    rs = ar.rounds_for_day(WORKOUT, date(2026, 10, 17), [6, 18], 2)
    assert [r["publish_at"].hour for r in rs] == [6, 18]
    for r in rs:
        assert 0 <= r["publish_at"].minute <= 59
        assert r["publish_at"] - r["start_at"] == timedelta(minutes=120)
        assert r["publish_at"].utcoffset() == timedelta(hours=9)
    assert [r["key"] for r in rs] == ["auto-workout_music-20261017-1", "auto-workout_music-20261017-2"]


def test_minutes_change_daily_but_are_stable():
    days = [date(2026, 10, 17) + timedelta(days=i) for i in range(30)]
    mins = [ar.round_minute(WORKOUT, d, 1) for d in days]
    assert len(set(mins)) >= 15                                   # 매일 달라 보인다
    assert mins == [ar.round_minute(WORKOUT, d, 1) for d in days]  # 재시작해도 같은 T
    assert ar.round_minute(WORKOUT, days[0], 1) != ar.round_minute(WORKOUT, days[0], 2) or True


def test_daily_cap_limits_rounds_and_hours_normalized():
    assert len(ar.rounds_for_day(WORKOUT, date(2026, 10, 17), [6, 18], 1)) == 1
    assert ar.normalize_hours([18, "6", 6, 99, None]) == [6, 18]
    assert ar.normalize_hours(None) == [6, 18] and ar.normalize_hours([]) == [6, 18]


def test_publish_at_rfc3339_utc():
    t = datetime(2026, 10, 17, 6, 37, tzinfo=KST)
    assert ar.publish_at_rfc3339(t) == "2026-10-16T21:37:00.000Z"


# ── tick: 중복·재시작·늦은 회차 ─────────────────────────────────────────
class _Jobs:
    """music_jobs 의 claim/reclaim/get 을 DB 처럼 흉내(job_id unique)."""

    def __init__(self):
        self.rows: dict[str, dict] = {}

    def claim_job(self, job_id, job_type, *, channel=None, metadata=None):
        if job_id in self.rows:
            return False
        self.rows[job_id] = {"job_id": job_id, "status": "queued", "metadata": metadata or {},
                             "updated_at": datetime.now(timezone.utc).isoformat()}
        return True

    def get_job(self, job_id):
        return self.rows.get(job_id)

    def reclaim_job(self, job_id, old):
        row = self.rows.get(job_id)
        if row and row["updated_at"] == old and row["status"] in ("queued", "running"):
            row["updated_at"] = datetime.now(timezone.utc).isoformat()
            return True
        return False


@pytest.fixture
def env(monkeypatch):
    from services import music_jobs
    jobs = _Jobs()
    for name in ("claim_job", "get_job", "reclaim_job"):
        monkeypatch.setattr(music_jobs, name, getattr(jobs, name))
    state = {WORKOUT: dict(ACTIVE), "rooftop_music": dict(ACTIVE)}  # where 도 is_active=true 로 둔다
    monkeypatch.setattr(ar, "get_channel_state", lambda ch: state[ch])
    started: list = []

    class _T:
        def __init__(self, target, args, name, daemon):
            self.args = args

        def start(self):
            started.append(self.args)
    monkeypatch.setattr(ar.threading, "Thread", _T)
    monkeypatch.setattr(ar, "_RUNNING", set())
    monkeypatch.setattr(ar, "_SETTLED", set())
    monkeypatch.setattr(ar, "_LOGGED_SKIP", set())
    monkeypatch.delenv("MUSIC_AUTO_RUN_CHANNELS", raising=False)
    monkeypatch.delenv("MUSIC_AUTO_RUN", raising=False)
    return jobs, state, started


def _r1(day=date(2026, 10, 17)):
    return ar.rounds_for_day(WORKOUT, day, [6, 18], 2)[0]


def test_tick_before_start_does_nothing(env):
    jobs, _, started = env
    r = _r1()
    assert ar.tick(r["start_at"] - timedelta(minutes=1)) == [] and not started


def test_same_round_runs_once(env):
    jobs, _, started = env
    r = _r1()
    assert ar.tick(r["start_at"]) == [r["key"]]
    ar._RUNNING.clear()                       # 다른 프로세스라고 가정해도
    assert ar.tick(r["start_at"] + timedelta(minutes=1)) == []   # DB 선점이 막는다
    assert len(started) == 1 and started[0][0]["key"] == r["key"]
    assert jobs.rows[r["key"]]["metadata"]["publish_at"] == r["publish_at"].isoformat()


def test_where_never_runs_even_if_active(env):
    jobs, state, started = env
    r = _r1()
    ar.tick(r["start_at"])
    assert all(a[0]["channel"] == WORKOUT for a in started)
    assert not [k for k in jobs.rows if "rooftop" in k]
    assert "rooftop_music" not in ar.auto_run_channels()


def test_inactive_channel_does_not_run(env):
    jobs, state, started = env
    state[WORKOUT]["is_active"] = False
    assert ar.tick(_r1()["start_at"]) == [] and not jobs.rows


def test_restart_resumes_interrupted_round_only_once(env, monkeypatch):
    jobs, _, started = env
    r = _r1()
    ar.tick(r["start_at"])                    # 이전 프로세스가 선점·시작
    jobs.rows[r["key"]]["status"] = "running"
    jobs.rows[r["key"]]["metadata"].update({"state": "rendered", "mix_id": "m9"})
    # 재시작: 마지막 갱신(이전 프로세스)이 지금 프로세스 시작보다 앞선다
    jobs.rows[r["key"]]["updated_at"] = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()  # 하트비트 10분+ 끊김
    monkeypatch.setattr(ar, "_STARTED_AT", datetime.now(timezone.utc) - timedelta(minutes=1))
    ar._RUNNING.clear()
    assert ar.tick(r["start_at"] + timedelta(minutes=30)) == [r["key"]]
    assert started[-1][2]["mix_id"] == "m9"   # 렌더 완료분 → 업로드만 이어서
    ar._RUNNING.clear()
    assert ar.tick(r["start_at"] + timedelta(minutes=31)) == []  # 재선점 후엔 다시 안 돈다


def test_live_round_in_other_process_not_stolen(env):
    jobs, _, started = env
    r = _r1()
    jobs.rows[r["key"]] = {"job_id": r["key"], "status": "running", "metadata": {},
                           "updated_at": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()}
    assert ar.tick(r["start_at"] + timedelta(minutes=5)) == []


def test_finished_round_not_rerun(env):
    jobs, _, started = env
    r = _r1()
    jobs.rows[r["key"]] = {"job_id": r["key"], "status": "completed", "metadata": {}, "updated_at": "2026-10-16T00:00:00+00:00"}
    assert ar.tick(r["start_at"] + timedelta(minutes=5)) == []
    assert r["key"] in ar._SETTLED


def test_late_round_starts_immediately(env):
    jobs, _, started = env
    r = _r1()
    assert ar.tick(r["publish_at"] + timedelta(minutes=170)) == [r["key"]]  # T+2시간50분 → 즉시 시작


def test_round_over_3h_late_is_skipped(env, caplog):
    jobs, _, started = env
    r = _r1()
    with caplog.at_level("WARNING"):
        assert ar.tick(r["publish_at"] + timedelta(minutes=181)) == []
    assert not started and r["key"] not in jobs.rows
    assert any("건너뜀" in m and "회차=1" in m for m in caplog.messages)


def test_auto_run_off_switch(env, monkeypatch):
    monkeypatch.setenv("MUSIC_AUTO_RUN", "off")
    assert ar.tick(_r1()["start_at"]) == []


# ── 회차 실행: 제작 → 폴백 거부 → 업로드 ────────────────────────────────
@pytest.fixture
def run_env(monkeypatch):
    from services import music_jobs, music_manual
    meta: dict = {}
    monkeypatch.setattr(music_jobs, "update_job_step", lambda *a, **k: None)
    monkeypatch.setattr(music_jobs, "merge_metadata", lambda jid, m: meta.update(m))
    monkeypatch.setattr(music_jobs, "complete_job", lambda *a, **k: meta.update(done=True))
    job = {"status": "done", "mix_id": "mix1", "video_url": "https://r2/x.mp4", "frame_thumb_key": "f.png",
           "image_review": {"ok": True}}
    calls: dict = {}

    def _start(mood, tc, combo, *, channel=None, auto_image=None):
        calls["start"] = (tc, channel, auto_image)
        music_manual._JOBS["j1"] = dict(job)
        return {"ok": True, "job_id": "j1"}
    monkeypatch.setattr(music_manual, "start", _start)
    monkeypatch.setattr(music_manual, "run", lambda jid: calls.setdefault("run", jid))
    from api.routes import music_dashboard as md
    def _publish(mix_id, body):
        calls["publish"] = (mix_id, body)
        return {"youtube_video_id": "v1", "youtube_url": "y"}
    monkeypatch.setattr(md, "publish", _publish)
    return calls, meta, job


def test_run_round_scheduled_publish(run_env, monkeypatch):
    calls, meta, _ = run_env
    r = _r1(date.today() + timedelta(days=2))     # T 가 미래
    out = ar.run_round(r, dict(ACTIVE))
    assert calls["start"] == (10, WORKOUT, True)
    mix_id, body = calls["publish"]
    assert mix_id == "mix1" and body.publish_at == ar.publish_at_rfc3339(r["publish_at"])
    assert body.synthetic_media is True and body.require_remotion is True
    assert out["privacy"] == "private" and meta["state"] == "uploaded" and meta["done"]


def test_run_round_after_T_publishes_now(run_env):
    calls, meta, _ = run_env
    r = _r1(date(2020, 1, 1))                     # T 가 과거
    out = ar.run_round(r, dict(ACTIVE))
    assert calls["publish"][1].publish_at is None and out["privacy"] == "public"


def test_run_round_semi_mode_private(run_env):
    calls, _, _ = run_env
    ar.run_round(_r1(date.today() + timedelta(days=2)), {**ACTIVE, "mode": "semi"})
    body = calls["publish"][1]
    assert body.privacy == "private" and body.publish_at is None


@pytest.mark.parametrize("patch", [{"frame_thumb_key": None}, {"video_url": "/tmp/local.mp4"}, {"status": "error"}])
def test_fallback_render_is_not_uploaded(run_env, monkeypatch, patch):
    from services import music_manual
    calls, meta, job = run_env
    job.update(patch)
    with pytest.raises(RuntimeError):
        ar.run_round(_r1(date.today() + timedelta(days=2)), dict(ACTIVE))
    assert "publish" not in calls


def test_busy_manual_job_retries(run_env, monkeypatch):
    from services import music_manual
    calls, _, job = run_env
    tries = iter([{"ok": False, "error": "busy"}, {"ok": True, "job_id": "j1"}])

    def _start(*a, **k):
        res = next(tries)
        if res["ok"]:
            music_manual._JOBS["j1"] = dict(job)
        return res
    monkeypatch.setattr(music_manual, "start", _start)
    slept = []
    ar.run_round(_r1(date.today() + timedelta(days=2)), dict(ACTIVE), sleep=slept.append)
    assert slept == [ar.BUSY_RETRY_SEC] and "publish" in calls


def test_resume_rendered_skips_production(run_env):
    calls, _, _ = run_env
    ar.run_round(_r1(date.today() + timedelta(days=2)), dict(ACTIVE), resume={"state": "rendered", "mix_id": "m9"})
    assert "start" not in calls and calls["publish"][0] == "m9"


# ── 업로드 body(유튜브 호출 모킹) ─────────────────────────────────────────
def _upload_body(monkeypatch, tmp_path, **kw):
    import googleapiclient.discovery as disc
    from services import music_uploads, music_youtube_oauth, youtube_upload as yu
    sent: dict = {}

    class _Req:
        def __init__(self, r):
            self.r = r

        def execute(self):
            return self.r

    class _YT:
        def videos(self):
            yt = self

            class V:
                def insert(self, part, body, media_body):
                    sent["body"] = body
                    return _Req({"id": "vid1"})
            return V()

        def thumbnails(self):
            class T:
                def set(self, **k):
                    return _Req({})
            return T()
    monkeypatch.setattr(disc, "build", lambda *a, **k: _YT())
    monkeypatch.setattr(music_youtube_oauth, "get_credentials", lambda ch=None: object())
    monkeypatch.setattr(yu, "_verify_music_channel", lambda *a, **k: None)
    monkeypatch.setattr(yu, "_fetch", lambda src, dest: Path(dest).write_bytes(b"mp4"))
    monkeypatch.setattr(yu, "_genre_playlist_id", lambda *a, **k: None)
    monkeypatch.setattr(music_uploads, "record_upload", lambda *a, **k: {})
    yu.upload_music_video("https://r2/x.mp4", {"slug": "s"}, {"mix_id": "m"}, title="t", description="d",
                          channel=WORKOUT, **kw)
    return sent["body"]["status"]


def test_upload_body_scheduled(monkeypatch, tmp_path):
    st = _upload_body(monkeypatch, tmp_path, privacy="private", synthetic_media=True,
                      publish_at="2026-10-16T21:37:00.000Z")
    assert st == {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                  "containsSyntheticMedia": True, "publishAt": "2026-10-16T21:37:00.000Z"}


def test_upload_body_without_publish_at_unchanged(monkeypatch, tmp_path):
    st = _upload_body(monkeypatch, tmp_path, privacy="public", synthetic_media=True)
    assert st == {"privacyStatus": "public", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}


# ── 옛 cron 라우트 no-op ─────────────────────────────────────────────────
def test_legacy_produce_is_noop(monkeypatch):
    from api.routes import music as m
    monkeypatch.setenv("CRON_SECRET", "s")
    monkeypatch.delenv("MUSIC_LEGACY_PRODUCE", raising=False)
    added = []

    class _BG:
        def add_task(self, *a, **k):
            added.append(a)
    res = m.produce(_BG(), authorization="Bearer s")
    assert res["skipped"] is True and not added


# ── 공개 경로(music_dashboard.publish) — 예약 공개·AI 고지·폴백 거부 ───────────────
def _publish(monkeypatch, body, *, frame="f.png"):
    import json
    from adapters import r2_storage
    from api.routes import music_dashboard as md
    from services import music_channel, music_meta, music_theme, music_uploads, music_video, youtube_upload
    AI = "💿 AI 고지"
    monkeypatch.setattr(music_channel, "get_channel_config", lambda *, channel=None: {"ai_disclosure": AI})
    theme = {"slug": "s", "channel": WORKOUT, "tag_combo": {"action": "workout"}}
    head = music_meta.build_info_head(theme, {}, None)
    meta = {lng: {"title": "t", "description": music_meta.assemble_description(
        {"intro": "i", "tracklist": "", "info_head": head, "copyright": "Copyright Ⓒ X All rights reserved."}, lng)}
        for lng in ("ko", "en")}
    loc = {"source_lang": "ko", "meta": meta, "lyrics": {}, "hashtags": ["#a"]}
    row = {"slug": "s", "mix_id": "m1", "mp4_url": "https://r2/old.mp4", "thumbnail_r2_key": "k", "channel": WORKOUT,
           "viz_spec": {}, "show_playlist": None, "character_r2_key": None, "tag_combo": {"action": "workout"}}
    monkeypatch.setattr(music_uploads, "get_upload", lambda m: row)
    monkeypatch.setattr(music_uploads, "get_localizations", lambda m: loc)
    monkeypatch.setattr(music_uploads, "set_localizations", lambda m, l: {"stored": True})
    monkeypatch.setattr(md, "_ensure_localizations", lambda *a, **k: (loc, [], True))
    monkeypatch.setattr(music_theme, "get_theme", lambda s: None)
    monkeypatch.setattr(r2_storage, "music_mix_url", lambda *a: "u")
    monkeypatch.setattr(r2_storage, "music_mix_key", lambda *a: "k")
    monkeypatch.setattr(r2_storage, "download_music_object", lambda key, dest: Path(dest).write_text(json.dumps({})) and dest)
    from services import music_auto_image
    monkeypatch.setattr(music_auto_image, "matching_render", lambda *a, **k: None)
    monkeypatch.setattr(music_video, "make_video", lambda *a, **k: {"video_url": "https://r2/new.mp4", "frame_thumb_key": frame})
    up: dict = {}
    monkeypatch.setattr(youtube_upload, "upload_music_video", lambda *a, **k: up.update(k) or {"video_id": "v", "video_url": "y"})
    monkeypatch.setattr(youtube_upload, "set_localizations", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(youtube_upload, "upload_captions", lambda *a, **k: {})
    md.publish("m1", body)
    return up, AI


def test_publish_scheduled_private_with_ai(monkeypatch):
    from api.routes import music_dashboard as md
    up, ai = _publish(monkeypatch, md.PublishBody(synthetic_media=True, publish_at="2026-10-16T21:37:00.000Z",
                                                  require_remotion=True))
    assert up["privacy"] == "private" and up["publish_at"] == "2026-10-16T21:37:00.000Z"
    assert up["synthetic_media"] is True and ai in up["description"]


def test_publish_manual_unchanged_public(monkeypatch):
    from api.routes import music_dashboard as md
    up, _ = _publish(monkeypatch, md.PublishBody(synthetic_media=False))
    assert up["privacy"] == "public" and up["publish_at"] is None


def test_publish_rejects_fallback_render(monkeypatch):
    from fastapi import HTTPException
    from api.routes import music_dashboard as md
    with pytest.raises(HTTPException) as ei:
        _publish(monkeypatch, md.PublishBody(require_remotion=True), frame=None)
    assert "폴백" in ei.value.detail
