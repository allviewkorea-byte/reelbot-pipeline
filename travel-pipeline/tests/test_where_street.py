"""where 배경 두 번째 스타일 "유럽 거리 필름 스냅" — 스타일 결정·프롬프트·검수·보관함/폴백·재개 E.

외부 호출(이미지·검수·R2·Supabase) 없이 전부 모킹.
"""

from __future__ import annotations

import random
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import music_auto_image as mai  # noqa: E402
from services import music_auto_run as ar  # noqa: E402
from services import music_where_image as mwi  # noqa: E402
from test_workout_image_reuse import _FakeS3  # noqa: E402

WHERE = "rooftop_music"
KST = ar.KST
ALLOWED = {"jazz", "cafe", "ballad", "breakup", "morning_drive", "citypop", "sunset_drive", "rnb_soul", "cafe_bgm"}


@pytest.fixture(autouse=True)
def _rate(monkeypatch):
    monkeypatch.delenv("MUSIC_WHERE_STREET_RATE", raising=False)


# ── A 스타일 결정 ─────────────────────────────────────────────────────
def test_allowed_genres_as_approved():
    assert mwi.STREET_GENRES == ALLOWED
    assert ALLOWED < set(mwi.WHERE_GENRES) and "bar_lounge" not in mwi.STREET_GENRES


def test_style_distribution_100_rounds():
    """where 회차 100회(장르 균등 랜덤) — 허용 장르 ≈40% 거리 스냅, 불허 장르 0%."""
    rng = random.Random(3)
    rounds = [(g, mwi.pick_style(g, rng=rng)) for g in (rng.choice(mwi.WHERE_GENRES) for _ in range(100))]
    allowed = [s for g, s in rounds if g in ALLOWED]
    assert all(s == "space" for g, s in rounds if g not in ALLOWED)
    assert 0.28 <= allowed.count("street") / len(allowed) <= 0.52, Counter(allowed)
    r9 = random.Random(9)
    big = Counter(mwi.pick_style("jazz", rng=r9) for _ in range(5000))
    assert abs(big["street"] / 5000 - 0.4) < 0.02


def test_rate_env(monkeypatch):
    monkeypatch.setenv("MUSIC_WHERE_STREET_RATE", "1")
    assert mwi.pick_style("cafe") == "street" and mwi.pick_style("lofi") == "space"
    monkeypatch.setenv("MUSIC_WHERE_STREET_RATE", "0")
    assert mwi.pick_style("cafe") == "space"
    monkeypatch.setenv("MUSIC_WHERE_STREET_RATE", "x")
    assert mwi.street_rate() == 0.4


def test_round_records_bg_style_and_injects(monkeypatch, caplog):
    from services import music_jobs, music_manual
    meta = {}
    monkeypatch.setattr(music_jobs, "merge_metadata", lambda jid, m: meta.update(m))
    monkeypatch.setattr(music_jobs, "list_recent_by_type", lambda *a, **k: [])
    monkeypatch.setattr(ar, "pick_where_genre", lambda ch, rng=None: "jazz")
    monkeypatch.setenv("MUSIC_WHERE_STREET_RATE", "1")
    got = {}

    def _start(mood, tc, combo, *, channel=None, auto_image=None):
        music_manual._JOBS["js"] = {"status": "running"}
        return {"ok": True, "job_id": "js"}

    def _run(jid):
        got["style"] = music_manual._JOBS[jid].get("image_style")
        music_manual._JOBS[jid].update(status="done", mix_id="m", video_url="https://x", frame_thumb_key="f")
    monkeypatch.setattr(music_manual, "start", _start)
    monkeypatch.setattr(music_manual, "run", _run)
    r = ar.rounds_for_day(WHERE, date(2026, 10, 19), [8, 21], 2)[0]
    with caplog.at_level("WARNING"):
        ar._produce(r, {"track_count": 1}, sleep=lambda s: None)
    assert meta["genre"] == "jazz" and meta["bg_style"] == "street" and got["style"] == "street"
    assert any("[auto-image] style=street genre=jazz" in rec.getMessage() for rec in caplog.records)


def test_workout_round_has_no_style(monkeypatch):
    from services import music_jobs, music_manual
    monkeypatch.setattr(music_jobs, "merge_metadata", lambda *a, **k: None)
    monkeypatch.setattr(ar, "_pick_image_action", lambda r: None)
    seen = {}

    def _start(mood, tc, combo, *, channel=None, auto_image=None):
        music_manual._JOBS["jw"] = {"status": "running"}
        return {"ok": True, "job_id": "jw"}

    def _run(jid):
        seen["style"] = music_manual._JOBS[jid].get("image_style")
        music_manual._JOBS[jid].update(status="done", mix_id="m", video_url="https://x", frame_thumb_key="f")
    monkeypatch.setattr(music_manual, "start", _start)
    monkeypatch.setattr(music_manual, "run", _run)
    ar._produce(ar.rounds_for_day("workout_music", date(2026, 10, 19), [6, 18], 2)[0], {"track_count": 1},
                sleep=lambda s: None)
    assert seen["style"] is None


# ── B 프롬프트 ───────────────────────────────────────────────────────
@pytest.mark.parametrize("month,season", [(3, "spring"), (5, "spring"), (6, "summer"), (8, "summer"),
                                          (9, "autumn"), (11, "autumn"), (12, "winter"), (1, "winter"), (2, "winter")])
def test_season_by_kst_month(month, season):
    assert mwi.season_of(month) == season
    p = mwi.build_street_prompt("jazz", now=datetime(2026, month, 15, 12, tzinfo=KST), rng=random.Random(1))
    assert mwi.SEASON_LINES[season] in p


def test_kst_boundary():
    # UTC 11/30 16:00 = KST 12/01 01:00 → 겨울
    from datetime import timezone
    assert mwi.current_season(datetime(2026, 11, 30, 16, tzinfo=timezone.utc)) == "winter"


@pytest.mark.parametrize("genre", sorted(ALLOWED))
def test_street_prompt_rules(genre):
    p = mwi.build_street_prompt(genre, ["간판 글자"], rng=random.Random(2), now=datetime(2026, 10, 19, tzinfo=KST))
    assert any(sc in p for sc in mwi.street_scene_pool(genre))
    for phrase in ("35mm 필름", "오른쪽 끝 1/3(가로 70~90% 지점)", "머리 위로 여백", "중앙은 하얗게 날리지 말 것",
                   "간판·명판·표지판·포스터 글자·브랜드 로고", "실존하는 특정 랜드마크", "인물은 1명", "정면 클로즈업 금지",
                   "붉은/버건디 포인트 한 가지", "이번엔 반드시 피할 것", "간판 글자"):
        assert phrase in p, phrase


def test_scene_pools_per_genre_group():
    assert mwi.street_scene_pool("cafe") == mwi.street_scene_pool("cafe_bgm")
    assert mwi.street_scene_pool("ballad") == mwi.street_scene_pool("breakup")
    assert mwi.street_scene_pool("citypop") == mwi.street_scene_pool("sunset_drive")
    assert all(6 <= len(v) <= 10 for v in mwi._STREET_SCENES.values())
    assert set(mwi._STREET_GENRE_GROUP) == ALLOWED


# ── C 검수 ───────────────────────────────────────────────────────────
def test_street_review_criteria():
    r = mwi.STREET_REVIEW_SYSTEM
    for phrase in ("인물 1명이 주인공이어도 된다", "브랜드 로고", "랜드마크", "손가락·손발", "얼굴 정면 클로즈업",
                   "노출이 과한 옷", "가로 가운데(로고 자리)", "중앙이 하얗게", "너무 어둡거나", '"pass"'):
        assert phrase in r, phrase
    assert "인물이 주인공인 사진" not in r and "자연 풍경 위주" not in r


# 기존 건축 공간 스타일(#341) 상수·프롬프트는 바이트 무변경 — main(dccc36b) 원본과 비교.
def test_space_style_constants_unchanged():
    import subprocess
    root = Path(__file__).resolve().parents[2]
    try:
        old = subprocess.run(["git", "show", "dccc36b:travel-pipeline/services/music_where_image.py"],
                             cwd=root, capture_output=True, text=True, check=True).stdout
    except Exception:  # noqa: BLE001 - git 이력 없는 환경(얕은 클론 등)이면 건너뜀
        pytest.skip("git 이력 없음")
    ns: dict = {}
    exec(compile(old, "old_mwi", "exec"), ns)
    for name in ("WHERE_GENRES", "PERSON_RATE", "WHERE_TONE", "_PERSON_LINE", "_NO_PERSON_LINE",
                 "_SCENES", "_GENRE_GROUP", "REVIEW_SYSTEM"):
        assert getattr(mwi, name) == ns[name], name
    for g in mwi.WHERE_GENRES:
        assert mwi.build_prompt(g, ["x"], rng=random.Random(4)) == ns["build_prompt"](g, ["x"], rng=random.Random(4))


def test_profile_street_vs_space():
    make, system, axis = mai._profile(None, WHERE, "jazz", style="street")
    assert system == mwi.STREET_REVIEW_SYSTEM and axis == "where-street/jazz" and "35mm 필름" in make([])
    make, system, axis = mai._profile(None, WHERE, "jazz", style="space")
    assert system == mwi.REVIEW_SYSTEM and axis == "where/jazz"
    assert mai._profile(None, WHERE, "jazz")[2] == "where/jazz"                     # 미지정 = 건축(기존)
    assert mai._profile("workout", "workout_music", None, style="street")[2] == "strength"   # 운동 무관
    assert mai._archive_dir("where-street/jazz") == "music-auto-bg/where-street/jazz/"
    assert mai._last_key("where-street/jazz") == "music-auto-bg/_last_where-street_jazz.txt"


def test_generate_uses_street_review(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(mai, "generate_image", lambda prompt, path: seen.setdefault("prompt", prompt) and Path(path).write_bytes(b"x") and {})
    monkeypatch.setattr(mai, "review_image", lambda path, system=None: seen.update(system=system) or {"pass": True, "reasons": []})
    res = mai.generate_reviewed(None, str(tmp_path / "bg.png"), channel=WHERE, genre="cafe", style="street")
    assert res["ok"] and seen["system"] == mwi.STREET_REVIEW_SYSTEM and "노천카페" in seen["prompt"]


# ── 보관함·폴백 ──────────────────────────────────────────────────────
@pytest.fixture
def s3(monkeypatch):
    from adapters import r2_storage
    from services import music_jobs
    fake = _FakeS3()
    monkeypatch.setattr(r2_storage, "is_available", lambda: True)
    monkeypatch.setattr(r2_storage, "_get_client", lambda: fake)
    monkeypatch.setattr(r2_storage, "upload_image",
                        lambda path, key, **kw: fake.add(key, Path(path).read_bytes()) or f"https://r2/{key}")
    fake.meta = {}
    monkeypatch.setattr(music_jobs, "merge_metadata", lambda jid, m: fake.meta.update(m))
    return fake


def _fail(monkeypatch):
    monkeypatch.setattr(mai, "generate_reviewed", lambda *a, **k: {"ok": False, "path": None, "attempts": [], "summary": "불합격"})


def test_street_pass_archived_separately(monkeypatch, tmp_path, s3):
    monkeypatch.setattr(mai, "generate_image", lambda prompt, path: Path(path).write_bytes(b"ST") and {})
    monkeypatch.setattr(mai, "review_image", lambda path, system=None: {"pass": True, "reasons": []})
    path, summary = mai.prepare_for_render("j", None, str(tmp_path), channel=WHERE, genre="jazz", style="street")
    keys = [k for k in s3.objs if k.endswith(".png")]
    assert len(keys) == 1 and keys[0].startswith("music-auto-bg/where-street/jazz/")
    assert summary["bg_style"] == "street" and s3.meta["auto_image"]["bg_style"] == "street"


def test_street_fallback_order(monkeypatch, tmp_path, s3):
    from adapters import r2_storage
    from services import music_uploads
    _fail(monkeypatch)
    monkeypatch.setattr(music_uploads, "list_thumbnail_keys", lambda ch: ["old/legacy.png"])
    monkeypatch.setattr(r2_storage, "download_music_object", lambda key, dest: Path(dest).write_bytes(b"LEGACY") and dest)
    s3.add("music-auto-bg/where-street/jazz/a.png", b"ST_JAZZ")
    s3.add("music-auto-bg/where-street/cafe/b.png", b"ST_CAFE", days_ago=90)
    s3.add("music-auto-bg/where/jazz/c.png", b"SP_JAZZ")
    s3.add("music-auto-bg/where/lofi/d.png", b"SP_LOFI", days_ago=90)
    go = lambda: mai.prepare_for_render("j", None, str(tmp_path), channel=WHERE, genre="jazz", style="street")  # noqa: E731
    order = []
    for drop in ("music-auto-bg/where-street/jazz/a.png", "music-auto-bg/where-street/cafe/b.png",
                 "music-auto-bg/where/jazz/c.png", "music-auto-bg/where/lofi/d.png", None):
        path, summary = go()
        order.append((Path(path).read_bytes(), summary["reused"].get("source")))
        if drop:
            s3.objs.pop(drop)
    assert order == [(b"ST_JAZZ", None), (b"ST_CAFE", "where_street_all"), (b"SP_JAZZ", "where_genre"),
                     (b"SP_LOFI", "where_all"), (b"LEGACY", "where_legacy")]
    monkeypatch.setattr(music_uploads, "list_thumbnail_keys", lambda ch: [])
    path, summary = go()
    assert path is None and summary["ok"] is False                                  # → 호출부 upload_gate


def test_space_reuse_never_picks_street(monkeypatch, tmp_path, s3):
    """건축 공간 재사용·전 장르 폴백(#343)은 거리 스냅 보관함을 보지 않는다(접두사 분리)."""
    from services import music_uploads
    _fail(monkeypatch)
    monkeypatch.setattr(music_uploads, "list_thumbnail_keys", lambda ch: [])
    s3.add("music-auto-bg/where-street/jazz/a.png", b"ST")
    path, summary = mai.prepare_for_render("j", None, str(tmp_path), channel=WHERE, genre="jazz")
    assert path is None and summary["bg_style"] == "space"


# ── D 수동 경로·재개 E ────────────────────────────────────────────────
def test_manual_where_unaffected():
    assert mai._profile(None, None, "jazz")[1] is None                              # 채널 None = 운동 기본(기존)
    assert mai.wants_auto_image(None, None) is False


def test_manual_run_passes_style_and_checkpoint(monkeypatch):
    from services import music_jobs, music_manual, music_produce
    meta: dict = {}
    for name in ("fail_job", "update_job_step", "touch"):
        monkeypatch.setattr(music_jobs, name, lambda *a, **k: None)
    monkeypatch.setattr(music_jobs, "merge_metadata", lambda jid, m: meta.update(m))
    monkeypatch.setattr(music_jobs, "start_job", lambda *a, **k: k.get("job_id"))
    monkeypatch.setattr(music_produce, "produce", lambda slug, **k: {"mix": {"mix_id": "m", "mp3_url": "u"}})
    got = {}
    monkeypatch.setattr(mai, "prepare_for_render", lambda *a, **k: got.update(k) or (None, {"ok": False}))
    jid = music_manual.start("jazz", 1, None, channel=WHERE, auto_image=True)["job_id"]
    music_manual._JOBS[jid]["image_style"] = "street"
    music_manual.run(jid)
    assert got["style"] == "street" and meta["recovery"]["bg_style"] == "street"
    assert music_manual._JOBS[jid]["fail_reason"] == "upload_gate"                   # 배경 없으면 렌더 전 중단


@pytest.fixture
def rjobs(monkeypatch):
    from services import music_jobs, music_uploads
    db: dict = {}
    monkeypatch.setattr(music_jobs, "merge_metadata", lambda jid, m: db.setdefault(jid, {}).update(m))
    monkeypatch.setattr(music_jobs, "touch", lambda jid: None)
    monkeypatch.setattr(music_jobs, "update_job_step", lambda *a, **k: None)
    monkeypatch.setattr(music_jobs, "complete_job", lambda jid, mix_id=None: db.setdefault(jid, {}).update(status="completed"))
    monkeypatch.setattr(music_jobs, "fail_job", lambda jid, err: db.setdefault(jid, {}).update(status="failed", err=err))
    monkeypatch.setattr(music_jobs, "get_job", lambda jid: None)
    monkeypatch.setattr(music_uploads, "set_channel", lambda *a: {})
    return db


def _rec(channel, **extra):
    return {"slug": "s1", "channel": channel, "auto_image": True, "tracks": [{"audio_id": "a1", "r2_key": "k"}],
            "theme": {"slug": "s1", "tag_combo": {"action": "workout"}}, "genre_id": extra.pop("genre_id", None),
            **extra}


def test_resume_e_keeps_axis_and_style(monkeypatch, rjobs):
    from services import music_recovery as rc
    calls = []
    monkeypatch.setattr(mai, "prepare_for_render", lambda job_id, action, d, **k: calls.append((action, k)) or ("/x.png", {}))
    monkeypatch.setattr(mai, "attach_after_render", lambda *a, **k: {})
    monkeypatch.setattr(rc, "recover_video", lambda rec, **k: ({"video_id": "m"}, {"ok": True}))
    rc._RECOVERING.acquire()  # 호출부(recover_stale_jobs)가 잡는 1개 제한 — _resume_safe 가 놓는다
    rc._resume_safe("w1", _rec("workout_music", image_action="running"))
    rc._RECOVERING.acquire()
    rc._resume_safe("w2", _rec(WHERE, genre_id="jazz", bg_style="street"))
    assert calls[0][0] == "running"                                                  # 운동 배경 축 유지
    assert calls[1][1]["style"] == "street" and calls[1][1]["genre"] == "jazz"
    assert rjobs["w1"]["status"] == rjobs["w2"]["status"] == "completed"


def test_resume_e_where_without_background_stops(monkeypatch, rjobs):
    from services import music_recovery as rc
    monkeypatch.setattr(mai, "prepare_for_render", lambda *a, **k: (None, {}))
    monkeypatch.setattr(rc, "recover_video", lambda *a, **k: pytest.fail("검은 배경 렌더 금지"))
    rc._RECOVERING.acquire()
    rc._resume_safe("w3", _rec(WHERE, genre_id="jazz", bg_style="street"))
    assert rjobs["w3"]["status"] == "failed" and "where 배경" in rjobs["w3"]["err"]
