"""쌍둥이 묵혀 쓰기 + 1곡 제목 + 불규칙 공개 시각 (대표 2026-11-16)."""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import music_auto_run as ar  # noqa: E402
from services import music_produce as mp  # noqa: E402
from services import music_twins as tw  # noqa: E402

NOW = datetime(2026, 11, 20, 3, 0, tzinfo=timezone.utc)


# ── 보관: 새 곡의 둘째 클립 맥락 저장 ─────────────────────────────────────
def _fake_suno(monkeypatch, calls):
    def gen(theme, log, **k):
        calls.append(theme)
        n = len(calls)
        return {"tracks": [{"audio_id": f"a{n}", "r2_key": f"k{n}a", "duration": 200},
                           {"audio_id": f"b{n}", "r2_key": f"k{n}b", "duration": 200}]}
    monkeypatch.setattr(mp, "_generate_with_retry", gen)
    monkeypatch.setattr(mp.music_store, "mark_track_used", lambda aid: True)
    monkeypatch.setattr(mp.music_master, "master_theme", lambda slug, p: [])
    monkeypatch.setattr(mp.music_mix, "build_mix", lambda *a, **k: {"mix_id": "m", "mp3_url": "u"})
    monkeypatch.setattr(mp.r2_storage, "is_available", lambda: False)


def test_new_song_saves_twin_with_context(monkeypatch):
    calls, saved = [], []
    _fake_suno(monkeypatch, calls)
    monkeypatch.setattr(mp.music_song_lang, "assign", lambda n, **k: ["en"] * n)
    monkeypatch.setattr(mp.music_lyrics, "generate_lyrics", lambda *a, **k: [
        {"title": "Morning Road", "lyrics": "la la", "language": "en", "sub_theme": "drive"}])
    monkeypatch.setattr(tw, "save", lambda ch, clip, ctx: saved.append((ch, clip["audio_id"], ctx)) or True)
    out = mp.produce("s1", n=1, genre_id=None, channel="rooftop_music", do_master=False, do_mix=False,
                     twin_meta={"tag_combo": None, "mood": "morning_drive"})
    assert [t["audio_id"] for t in out["produced"]] == ["a1"]            # 영상엔 첫 클립만
    assert len(saved) == 1 and saved[0][1] == "b1"                        # 둘째 클립은 보관
    ctx = saved[0][2]
    assert ctx["language"] == "en" and ctx["lyrics"] == "la la" and ctx["mood"] == "morning_drive"


def test_manual_path_does_not_save_twin(monkeypatch):
    calls, saved = [], []
    _fake_suno(monkeypatch, calls)
    monkeypatch.setattr(tw, "save", lambda *a: saved.append(a) or True)
    mp.produce("s2", n=1, track_type="instrumental", channel="workout_music", do_master=False, do_mix=False)
    assert saved == [] and mp._TWIN_SINK.items is None


def test_instrumental_no_immediate_recycle(monkeypatch):
    """남은 곡을 바로 다음 회차에 다시 쓰던 즉시 재활용은 꺼졌다(묵혀 쓰기로만)."""
    calls = []
    _fake_suno(monkeypatch, calls)
    monkeypatch.setattr(mp.music_store, "find_unused_track",
                        lambda *a, **k: pytest.fail("즉시 재활용 조회가 일어나면 안 됨"))
    mp.produce("s3", n=1, track_type="instrumental", genre_id=None, channel="workout_music",
               do_master=False, do_mix=False)
    assert len(calls) == 1


# ── 사용: 묵힌 곡이면 Suno 없이 ───────────────────────────────────────────
def test_produce_from_twin_skips_suno(monkeypatch):
    marked = []
    monkeypatch.setattr(mp, "_generate_with_retry", lambda *a, **k: pytest.fail("Suno 호출 금지"))
    monkeypatch.setattr(mp.music_store, "mark_track_used", lambda aid: marked.append(aid) or True)
    monkeypatch.setattr(mp.music_master, "master_theme", lambda slug, p: [])
    monkeypatch.setattr(mp.music_mix, "build_mix", lambda slug, p, **k: {"mix_id": "m", "mp3_url": "u", "lyr": k.get("lyrics_by_id")})
    monkeypatch.setattr(mp.r2_storage, "is_available", lambda: False)
    twin = {"audio_id": "b9", "r2_key": "k", "duration": 210, "title": "Night Walk",
            "language": "en", "lyrics": "oh oh", "tags": "pop"}
    out = mp.produce("s4", n=1, channel="rooftop_music", twin=twin)
    assert marked == ["b9"] and out["twin"] == "b9"
    assert out["songs"][0]["lyrics"] == "oh oh" and out["mix"]["lyr"] == {"b9": "oh oh"}
    assert out["produced"][0]["language"] == "en"


# ── 선택: 7일 이상·맥락 있는 것만, 오래된 순 ────────────────────────────────
def test_pick_rules(monkeypatch):
    seen_cutoff = []
    rows = [
        {"audio_id": "old_noctx", "r2_key": "k", "duration": 200, "genre": "jazz"},
        {"audio_id": "short", "r2_key": "k", "duration": 30, "genre": "jazz"},
        {"audio_id": "nolang", "r2_key": "k", "duration": 200, "genre": "jazz"},
        {"audio_id": "good", "r2_key": "k", "duration": 200, "genre": "jazz", "created_at": "x"},
        {"audio_id": "later", "r2_key": "k", "duration": 200, "genre": "jazz"},
    ]
    ctxs = {"short": {"language": "inst"}, "nolang": {"title": "?"},
            "good": {"language": "inst", "title": "Blue"}, "later": {"language": "inst"}}
    from adapters import r2_storage
    from services import music_store
    monkeypatch.setattr(music_store, "list_aged_unused",
                        lambda ch, older_than_iso, limit=20: seen_cutoff.append(older_than_iso) or rows)
    monkeypatch.setattr(r2_storage, "get_twin_ctx", lambda ch, aid: ctxs.get(aid))
    got = tw.pick("rooftop_music", now=NOW)
    assert got["audio_id"] == "good" and got["genre_id"] == "jazz" and got["title"] == "Blue"
    assert seen_cutoff == [(NOW - timedelta(days=7)).isoformat()]


def test_pick_vocal_needs_lyrics_and_switch(monkeypatch):
    from adapters import r2_storage
    from services import music_store
    monkeypatch.setattr(music_store, "list_aged_unused",
                        lambda ch, older_than_iso, limit=20: [{"audio_id": "v", "r2_key": "k", "duration": 200}])
    monkeypatch.setattr(r2_storage, "get_twin_ctx", lambda ch, aid: {"language": "en", "lyrics": ""})
    assert tw.pick("workout_music", now=NOW) is None
    monkeypatch.setattr(r2_storage, "get_twin_ctx", lambda ch, aid: {"language": "en", "lyrics": "x"})
    assert tw.pick("workout_music", now=NOW)["audio_id"] == "v"
    monkeypatch.setenv("MUSIC_TWIN_REUSE", "off")
    assert tw.pick("workout_music", now=NOW) is None


# ── 1곡 제목: playlist 접두어 없음 ─────────────────────────────────────────
def test_single_song_title_has_no_playlist_prefix(monkeypatch):
    from services import music_meta
    monkeypatch.setattr(music_meta, "_generate_title_copy", lambda t, v: ("출근길에 틀면 달라짐", "Morning Drive"))
    assert music_meta.build_title({"slug": "t1", "track_count": 1}, {}) == "출근길에 틀면 달라짐 | Morning Drive"
    assert music_meta.build_title({"slug": "t2", "track_count": 10}, {}).startswith("playlist🎧 ")


# ── 불규칙 공개 시각 ────────────────────────────────────────────────────
def test_random_hour_window_gap_and_daily_change(monkeypatch):
    monkeypatch.delenv("MUSIC_RANDOM_HOUR_WINDOW", raising=False)
    monkeypatch.delenv("MUSIC_AUTO_RUN_CHANNELS", raising=False)
    hours_seen = set()
    for i in range(60):
        d = date(2026, 11, 1) + timedelta(days=i)
        w = ar.rounds_for_day("workout_music", d, [6, 18], 1)[0]["publish_at"]
        r = ar.rounds_for_day(ar.WHERE_CHANNEL, d, [8, 21], 1)[0]["publish_at"]
        assert 10 <= w.hour <= 23 and 10 <= r.hour <= 23
        assert abs(w.hour - r.hour) >= ar.RANDOM_HOUR_MIN_GAP_H
        hours_seen.add(w.hour)
        assert ar.rounds_for_day("workout_music", d, [6, 18], 1)[0]["publish_at"] == w   # 결정적
    assert len(hours_seen) >= 8                                                        # 매일 바뀜


def test_random_hour_off_and_multi_slot_keep_fixed(monkeypatch):
    d = date(2026, 11, 20)
    monkeypatch.setenv("MUSIC_RANDOM_HOUR_WINDOW", "off")
    assert ar.rounds_for_day("workout_music", d, [6, 18], 1)[0]["publish_at"].hour == 6
    monkeypatch.delenv("MUSIC_RANDOM_HOUR_WINDOW", raising=False)
    assert [r["publish_at"].hour for r in ar.rounds_for_day("workout_music", d, [6, 18], 2)] == [6, 18]
    monkeypatch.setenv("MUSIC_RANDOM_HOUR_WINDOW", "12-14")
    assert 12 <= ar.rounds_for_day("workout_music", d, [6, 18], 1)[0]["publish_at"].hour <= 14


# ── 자동 회차: 묵힌 곡이 있으면 그 곡의 장르·태그로, 없으면 평소대로 ───────────────
def _harness(monkeypatch, twin):
    from services import music_jobs, music_manual
    monkeypatch.setattr(music_jobs, "merge_metadata", lambda *a, **k: None)
    monkeypatch.setattr(music_jobs, "list_recent_by_type", lambda *a, **k: [])
    monkeypatch.setattr(tw, "pick", lambda ch, **k: twin)
    got = {}

    def _start(mood, tc, combo, *, channel=None, auto_image=None, **kw):
        got.update(mood=mood, combo=combo, **kw)
        music_manual._JOBS["jt"] = {"status": "done", "mix_id": "m", "video_url": "https://x", "frame_thumb_key": "f"}
        return {"ok": True, "job_id": "jt"}
    monkeypatch.setattr(music_manual, "start", _start)
    monkeypatch.setattr(music_manual, "run", lambda jid: None)
    return got


def test_auto_where_uses_twin_genre(monkeypatch):
    got = _harness(monkeypatch, {"audio_id": "b1", "genre_id": "citypop", "language": "en"})
    r = ar.rounds_for_day(ar.WHERE_CHANNEL, date.today() + timedelta(days=1), [8, 21], 1)[0]
    ar._produce(r, {"track_count": 1}, sleep=lambda s: None)
    assert got["mood"] == "citypop" and got["twin"]["audio_id"] == "b1" and got["keep_twin"] is True


def test_auto_workout_uses_twin_combo_and_multi_track_skips_twin(monkeypatch):
    combo = {"action": "workout", "genre": ["house"]}
    got = _harness(monkeypatch, {"audio_id": "b2", "tag_combo": combo, "language": "inst"})
    r = ar.rounds_for_day("workout_music", date.today() + timedelta(days=1), [6, 18], 1)[0]
    ar._produce(r, {"track_count": 1}, sleep=lambda s: None)
    assert got["combo"] == combo and got["twin"]["audio_id"] == "b2"
    got.clear()
    ar._produce(r, {"track_count": 10}, sleep=lambda s: None)              # 여러 곡 영상은 묵힌 곡 안 씀
    assert got["twin"] is None and got["combo"] is None
