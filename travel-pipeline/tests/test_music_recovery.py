"""음악 제작 자동 복구(A~G) — 외부 호출(Suno·Lambda·R2·Claude) 없이 모킹."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import music_recovery as rc  # noqa: E402

OK_VIDEO = {"video_id": "mix1", "video_url": "https://r2/mix1.mp4", "frame_thumb_key": "f.png", "duration": 600.0}


@pytest.fixture
def jobs(monkeypatch):
    """music_jobs 를 메모리 DB 로."""
    from services import music_jobs
    db: dict[str, dict] = {}

    def merge(jid, extra):
        row = db.setdefault(jid, {"job_id": jid, "metadata": {}, "status": "running"})
        row["metadata"] = {**row["metadata"], **extra}

    monkeypatch.setattr(music_jobs, "merge_metadata", merge)
    monkeypatch.setattr(music_jobs, "touch", lambda jid: None)
    monkeypatch.setattr(music_jobs, "update_job_step", lambda *a, **k: None)
    monkeypatch.setattr(music_jobs, "complete_job", lambda jid, mix_id=None: db.setdefault(jid, {}).update(status="completed", mix_id=mix_id))
    monkeypatch.setattr(music_jobs, "fail_job", lambda jid, err: db.setdefault(jid, {}).update(status="failed", error_message=err))
    monkeypatch.setattr(music_jobs, "get_job", lambda jid: db.get(jid))
    return db


@pytest.fixture
def uploads(monkeypatch):
    from services import music_uploads
    marks: list = []
    monkeypatch.setattr(music_uploads, "mark_render_failed", lambda mix_id, reason, clear_mp4=False: marks.append((mix_id, reason, clear_mp4)) or {})
    monkeypatch.setattr(music_uploads, "set_channel", lambda *a: {})
    return marks


# ── B 렌더 검증 ───────────────────────────────────────────────────────
def test_check_render_fallback_and_local_path(monkeypatch):
    monkeypatch.setenv("MUSIC_RENDER_CHECK", "off")
    assert rc.check_render({**OK_VIDEO, "frame_thumb_key": None})["ok"] is False          # Remotion 폴백
    r = rc.check_render({**OK_VIDEO, "video_url": "/tmp/makevid_x/mix1.mp4"})              # R2 업로드 실패
    assert r["ok"] is False and "로컬" in r["reason"]
    assert rc.check_render(OK_VIDEO)["ok"] is True


@pytest.mark.parametrize("all_logo,ok", [(False, False), (True, True)])
def test_check_render_vision_sheet(monkeypatch, all_logo, ok):
    monkeypatch.delenv("MUSIC_RENDER_CHECK", raising=False)
    monkeypatch.setattr(rc, "build_contact_sheet", lambda url, times, dest: Path(dest).write_bytes(b"jpg") and dest)
    monkeypatch.setattr(rc, "_logo_text", lambda ch: "GYM;_____")
    seen = {}

    def _vision(path, logo, cells):
        seen.update(logo=logo, cells=cells)
        return {"all_logo": all_logo, "missing_cells": [] if all_logo else [3], "note": "", "model": "m"}
    monkeypatch.setattr(rc, "vision_logo_check", _vision)
    r = rc.check_render(OK_VIDEO, channel="workout_music")
    assert r["ok"] is ok and seen["logo"] == "GYM;_____" and seen["cells"] == len(rc.frame_times(600.0))


def test_vision_failure_only_skips_that_check(monkeypatch):
    monkeypatch.delenv("MUSIC_RENDER_CHECK", raising=False)
    monkeypatch.setattr(rc, "build_contact_sheet", lambda *a: (_ for _ in ()).throw(RuntimeError("ffmpeg")))
    r = rc.check_render(OK_VIDEO)
    assert r["ok"] is True and "skipped" in r["vision"]


def test_frame_times_one_per_chunk():
    from services import music_video
    t = rc.frame_times(39.7 * 60)
    assert len(t) == len(music_video._plan_chunks(39.7 * 60)) and t == sorted(t) and t[-1] < 39.7 * 60


def test_contact_sheet_real_ffmpeg(tmp_path):
    mp4 = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=5",
                    "-t", "12", "-pix_fmt", "yuv420p", str(mp4)], check=True)
    out = rc.build_contact_sheet(str(mp4), [1.0, 4.0, 7.0, 10.0, 11.0], str(tmp_path / "s.jpg"))
    dims = subprocess.run(["ffprobe", "-loglevel", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", out],
                          capture_output=True, text=True).stdout.strip()
    w, h = map(int, dims.split(","))
    assert w > 4 * 480 and h > 2 * 270  # 4칸 × 2줄


# ── C 영상 단계 재시도(같은 곡, Suno 0회) ───────────────────────────────
REC = {"slug": "s1", "theme": {"slug": "s1", "title_kr": "원래 제목", "tag_combo": {"action": "workout"}},
       "channel": "workout_music", "tracks": [{"audio_id": "a1", "r2_key": "k1"}], "mix_id": "mix1", "minutes": 3.5}


def test_render_exception_retries_with_same_tracks_no_suno(monkeypatch, jobs, uploads):
    from services import music_suno, music_video, music_viz_analyzer
    monkeypatch.setattr(music_suno, "generate_and_store", lambda *a, **k: pytest.fail("Suno 호출 금지"))
    monkeypatch.setattr(rc, "_load_mix", lambda slug, mix_id: {"mix_id": mix_id, "mp3_url": "u", "tracks": []})
    monkeypatch.setattr(music_viz_analyzer, "analyze_song", lambda theme, mix: {})
    calls = []
    monkeypatch.setattr(music_video, "make_video", lambda theme, mix, **k: calls.append((theme, mix["mix_id"])) or dict(OK_VIDEO))
    monkeypatch.setenv("MUSIC_RENDER_CHECK", "off")
    video, chk = rc.recover_video(REC, job_id="j", first_error=RuntimeError("Lambda boom"), sleep=lambda s: None)
    assert chk["ok"] and video["video_id"] == "mix1"
    assert calls[0][0]["title_kr"] == "원래 제목" and calls[0][1] == "mix1"  # 원래 주제·같은 mix → 큐 행 덮어씀
    assert jobs["j"]["metadata"]["recovery_status"].startswith("복구 성공")


def test_fallback_then_retry_success_replaces_row(monkeypatch, jobs, uploads):
    from services import music_video, music_viz_analyzer
    monkeypatch.setattr(rc, "_load_mix", lambda slug, mix_id: {"mix_id": mix_id, "mp3_url": "u", "tracks": []})
    monkeypatch.setattr(music_viz_analyzer, "analyze_song", lambda theme, mix: {})
    outs = iter([{**OK_VIDEO, "frame_thumb_key": None}, dict(OK_VIDEO)])
    monkeypatch.setattr(music_video, "make_video", lambda *a, **k: next(outs))
    monkeypatch.setenv("MUSIC_RENDER_CHECK", "off")
    first = rc.RenderFailed("Remotion 렌더 실패(ffmpeg 폴백 — 로고 없음)", dict(OK_VIDEO, frame_thumb_key=None))
    video, _ = rc.recover_video(REC, job_id="j", first_error=first, sleep=lambda s: None)
    assert video["frame_thumb_key"] == "f.png"
    assert uploads[0][0] == "mix1" and "폴백" in uploads[0][1]   # 실패 표시 → 재렌더 성공이 같은 mix_id 로 pending 복귀
    assert len(uploads) == 2                                      # 첫 시도·1차 재시도 실패분


def test_retry_exhausted_marks_render_failed(monkeypatch, jobs, uploads):
    from services import music_video, music_viz_analyzer
    monkeypatch.setattr(rc, "_load_mix", lambda slug, mix_id: {"mix_id": mix_id, "mp3_url": "u", "tracks": []})
    monkeypatch.setattr(music_viz_analyzer, "analyze_song", lambda theme, mix: {})
    monkeypatch.setattr(music_video, "make_video", lambda *a, **k: {**OK_VIDEO, "frame_thumb_key": None})
    monkeypatch.setenv("MUSIC_RENDER_CHECK", "off")
    slept = []
    with pytest.raises(RuntimeError, match="복구 2회 실패"):
        rc.recover_video(REC, job_id="j", first_error=RuntimeError("x"), sleep=slept.append)
    assert slept == [60, 60] and uploads and all(u[0] == "mix1" for u in uploads)
    assert jobs["j"]["metadata"]["recovery_status"].startswith("복구 실패")


def test_local_mp4_url_is_cleared_from_queue(monkeypatch, jobs, uploads):
    rc.mark_failed_row({"video_id": "mix9", "video_url": "/tmp/makevid_1/mix9.mp4"}, "mp4 R2 업로드 실패(로컬 경로)")
    assert uploads == [("mix9", "mp4 R2 업로드 실패(로컬 경로)", True)]


def test_rebuild_mix_when_mix_missing(monkeypatch):
    from services import music_master, music_mix, music_store
    monkeypatch.setattr(music_store, "get_tracks_by_ids", lambda ids, channel=None: [{"audio_id": "a1", "r2_key": "k1"}])
    monkeypatch.setattr(music_master, "master_theme", lambda slug, rows: rows)
    monkeypatch.setattr(rc, "_load_lyrics", lambda slug, ids: {"a1": "가사"})
    got = {}
    monkeypatch.setattr(music_mix, "build_mix", lambda slug, rows, **k: got.update(k) or {"mix_id": "new", "mp3_url": "u"})
    mix = rc.rebuild_mix({**REC, "mix_id": None})
    assert mix["mix_id"] == "new" and got["lyrics_by_id"] == {"a1": "가사"} and got["minutes"] == 3.5


# ── D 부분 실패 보충 ───────────────────────────────────────────────────
def _produce_env(monkeypatch, fail_first: int):
    from services import music_lyrics, music_produce, music_store
    lyr_calls = []

    def _lyrics(theme, n, **k):
        lyr_calls.append(n)
        return [{"title": f"t{len(lyr_calls)}-{i}", "lyrics": "가사", "style": "pop"} for i in range(n)]
    monkeypatch.setattr(music_lyrics, "generate_lyrics", _lyrics)
    gen = {"n": 0}

    def _gen(theme, **k):
        gen["n"] += 1
        if gen["n"] <= fail_first:
            raise RuntimeError("suno fail")
        return {"task_id": f"t{gen['n']}", "tracks": [{"audio_id": f"a{gen['n']}", "r2_key": f"k{gen['n']}"},
                                                      {"audio_id": f"b{gen['n']}", "r2_key": "x"}]}
    from services import music_suno
    monkeypatch.setattr(music_suno, "generate_and_store", _gen)
    monkeypatch.setattr(music_store, "mark_track_used", lambda aid: True)
    monkeypatch.setattr(music_produce.r2_storage, "is_available", lambda: False)
    return music_produce, lyr_calls, gen


def test_partial_failure_tops_up_only_missing(monkeypatch):
    mp, lyr_calls, gen = _produce_env(monkeypatch, fail_first=3)
    events = []
    out = mp.produce("s", n=10, do_master=False, do_mix=False, checkpoint=events.append)
    assert len(out["produced"]) == 10
    assert lyr_calls == [10, 3] and gen["n"] == 13          # 실패 3곡분만 추가(Suno 13회)
    assert len([e for e in events if e["type"] == "track"]) == 10
    assert len([e for e in events if e["type"] == "task"]) == 0  # stub 은 on_task 를 안 부름(실제는 제출 직후)


def test_zero_success_does_not_regenerate(monkeypatch):
    mp, lyr_calls, gen = _produce_env(monkeypatch, fail_first=99)
    with pytest.raises(RuntimeError, match="전 곡 실패"):
        mp.produce("s", n=3, do_master=False, do_mix=False)
    assert lyr_calls == [3] and gen["n"] == 3


def test_where_suno_body_unchanged_with_checkpoint(monkeypatch):
    """where 정상 경로 — 체크포인트 유무와 무관하게 Suno 로 가는 theme(=요청 body 입력)이 같다."""
    from services import music_suno
    bodies = {}
    for label, cp in (("off", None), ("on", lambda e: None)):
        mp, _, _ = _produce_env(monkeypatch, fail_first=0)
        sent = []
        monkeypatch.setattr(music_suno, "generate_and_store", lambda theme, **k: sent.append(dict(theme)) or
                            {"task_id": "t", "tracks": [{"audio_id": f"a{len(sent)}", "r2_key": "k"}]})
        monkeypatch.setattr("random.choice", lambda seq: seq[0])
        monkeypatch.setattr("random.shuffle", lambda seq: None)
        mp.produce("s", n=2, do_master=False, do_mix=False, checkpoint=cp)
        bodies[label] = [music_suno._build_body(t) for t in sent]
    assert bodies["off"] == bodies["on"]


# ── F 곡 저장 재시도·taskId 보존 ──────────────────────────────────────
def test_store_retry_then_success(monkeypatch):
    from services import music_suno
    n = {"c": 0}

    def _store(*a, **k):
        n["c"] += 1
        if n["c"] <= 2:
            raise RuntimeError("R2 down")
        return [{"audio_id": "a1"}]
    monkeypatch.setattr(music_suno, "store_tracks", _store)
    slept = []
    assert music_suno.store_with_retry("s", "task1", [{}], sleep=slept.append) == [{"audio_id": "a1"}]
    assert slept == [2, 4]


def test_store_fails_keeps_task_id_in_checkpoint(monkeypatch, jobs):
    from services import music_produce, music_suno
    monkeypatch.setattr(music_suno, "submit_generation", lambda theme: "task77")
    monkeypatch.setattr(music_suno, "poll_task", lambda tid, **k: [{"audio_id": "a1", "audio_url": "https://cdn/a1.mp3"}])
    monkeypatch.setattr(music_suno, "store_tracks", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("R2 down")))
    monkeypatch.setattr(music_suno.time, "sleep", lambda s: None)
    cp = rc.Checkpoint("j", {"slug": "s", "track_count": 1})
    with pytest.raises(music_suno.StoreFailed):
        music_produce._generate_with_retry({"theme_slug": "s", "genre_id": "g", "channel": "workout_music"}, print, checkpoint=cp)
    meta = jobs["j"]["metadata"]["recovery"]
    assert meta["task_ids"] == ["task77"]
    assert meta["pending_store"][0]["task_id"] == "task77" and meta["pending_store"][0]["audio_urls"] == ["https://cdn/a1.mp3"]


def test_reacquire_pending_stores(monkeypatch, jobs):
    from services import music_jobs
    jobs["old"] = {"job_id": "old", "status": "failed", "metadata": {"recovery": {
        "slug": "s", "tracks": [], "pending_store": [{"task_id": "task77", "slug": "s", "genre": "g", "channel": "workout_music"}]}}}
    monkeypatch.setattr(music_jobs, "list_recent_with_metadata", lambda limit=50: list(jobs.values()))
    monkeypatch.setattr(rc, "reacquire", lambda item, **k: [{"audio_id": "a1", "r2_key": "k1"}, {"audio_id": "b1"}])
    assert rc.reacquire_pending_stores() == 1
    rec = jobs["old"]["metadata"]["recovery"]
    assert rec["pending_store"] == [] and rec["tracks"] == [{"audio_id": "a1", "r2_key": "k1", "duration": None, "title": None, "tags": None}]


# ── E 재시작 복구 ─────────────────────────────────────────────────────
def _row(jid, minutes_ago, rec=None, jtype="manual_render"):
    return {"job_id": jid, "type": jtype, "status": "running",
            "updated_at": (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat(),
            "metadata": {"recovery": rec} if rec else {}}


def test_stale_rule_heartbeat_and_server_start(monkeypatch):
    monkeypatch.setattr(rc, "_STARTED_AT", datetime.now(timezone.utc))
    assert rc.is_stale(_row("a", 11)) is True
    assert rc.is_stale(_row("b", 5)) is False                       # 하트비트 살아 있음
    monkeypatch.setattr(rc, "_STARTED_AT", datetime.now(timezone.utc) - timedelta(minutes=30))
    assert rc.is_stale(_row("c", 11)) is False                      # 이 서버 시작 후 갱신된 작업


def test_restart_resumes_or_cleans(monkeypatch, jobs, uploads):
    from services import music_jobs, music_manual
    monkeypatch.setattr(rc, "_STARTED_AT", datetime.now(timezone.utc))
    rows = [_row("nosongs", 15), _row("withsongs", 20, dict(REC)), _row("auto", 30, jtype="auto_run"), _row("live", 2, dict(REC))]
    for r in rows:
        jobs[r["job_id"]] = r
    monkeypatch.setattr(music_jobs, "list_unfinished", lambda: rows)
    monkeypatch.setattr(music_jobs, "reclaim_job", lambda jid, old: True)
    rendered = []
    monkeypatch.setattr(rc, "recover_video", lambda rec, **k: (rendered.append(rec["slug"]) or dict(OK_VIDEO), {"ok": True}))
    h1 = rc.recover_stale_jobs(run_async=False)
    assert h1 == ["nosongs", "withsongs"]
    assert jobs["nosongs"]["status"] == "failed" and "서버 재시작" in jobs["nosongs"]["error_message"]
    assert jobs["withsongs"]["status"] == "completed" and jobs["withsongs"]["mix_id"] == "mix1"
    assert rendered == ["s1"]                                       # Suno 없이 같은 곡으로 영상만
    assert jobs["auto"]["status"] == "running" and jobs["live"]["status"] == "running"
    assert music_manual._active_job is None                         # 복구가 잡았던 락 해제


def test_restart_recovery_waits_for_running_manual_job(monkeypatch, jobs):
    from services import music_jobs, music_manual
    monkeypatch.setattr(rc, "_STARTED_AT", datetime.now(timezone.utc))
    monkeypatch.setattr(music_jobs, "list_unfinished", lambda: [_row("withsongs", 20, dict(REC))])
    monkeypatch.setattr(music_manual, "_JOBS", {"busy": {"status": "running"}})
    monkeypatch.setattr(music_manual, "_active_job", "busy")
    assert rc.recover_stale_jobs(run_async=False) == []             # 동시 1개 — 다음 tick


def test_checkpoint_accumulates(jobs):
    cp = rc.Checkpoint("j", {"slug": "s", "track_count": 3, "theme": {"slug": "s"}})
    cp({"type": "task", "task_id": "t1"})
    cp({"type": "track", "record": {"audio_id": "a1", "r2_key": "k"}})
    cp({"type": "track", "record": {"audio_id": "a1", "r2_key": "k"}})  # 중복 무시
    rec = jobs["j"]["metadata"]["recovery"]
    assert rec["task_ids"] == ["t1"] and len(rec["tracks"]) == 1 and rec["requested"] == 3 and rec["slug"] == "s"


# ── 통합: 수동 생성 경로(자동 회차가 쓰는 경로) ───────────────────────────
def test_manual_run_fallback_recovers_without_suno(monkeypatch, jobs, uploads):
    from services import music_manual, music_produce, music_video, music_viz_analyzer, music_uploads
    suno = {"n": 0}

    def _produce(slug, **k):
        suno["n"] += 1
        cp = k["checkpoint"]
        cp({"type": "task", "task_id": "t1"})
        cp({"type": "track", "record": {"audio_id": "a1", "r2_key": "k1"}})
        return {"mix": {"mix_id": "mix1", "mp3_url": "u", "tracks": []}}
    monkeypatch.setattr(music_produce, "produce", _produce)
    monkeypatch.setattr(music_viz_analyzer, "analyze_song", lambda theme, mix: {})
    monkeypatch.setattr(rc, "_load_mix", lambda slug, mix_id: {"mix_id": mix_id, "mp3_url": "u", "tracks": []})
    outs = iter([{**OK_VIDEO, "frame_thumb_key": None}, dict(OK_VIDEO)])
    monkeypatch.setattr(music_video, "make_video", lambda *a, **k: next(outs))
    monkeypatch.setattr(music_uploads, "set_channel", lambda *a: {})
    monkeypatch.setattr(rc, "RETRY_WAIT_SEC", 0)
    monkeypatch.setattr(rc.time, "sleep", lambda s: None)
    monkeypatch.setenv("MUSIC_RENDER_CHECK", "off")
    from services import music_jobs
    monkeypatch.setattr(music_jobs, "start_job", lambda *a, **k: k.get("job_id"))
    started = music_manual.start(None, 1, None, channel=None, auto_image=False)
    music_manual.run(started["job_id"])
    st = music_manual._JOBS[started["job_id"]]
    assert st["status"] == "done" and st["mix_id"] == "mix1" and st["frame_thumb_key"] == "f.png"
    assert suno["n"] == 1                                   # Suno(곡 생성)는 처음 1번뿐
    assert uploads and uploads[0][0] == "mix1"              # 폴백분은 render_failed 로 표시 후 교체
    rec = jobs[started["job_id"]]["metadata"]["recovery"]
    assert rec["tracks"] == [{"audio_id": "a1", "r2_key": "k1"}] and rec["task_ids"] == ["t1"]
