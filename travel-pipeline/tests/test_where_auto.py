"""where 자동화 — 회차·장르 선택·이미지 프로필·해시태그·제목 한국어 검증(외부 호출 없음)."""

from __future__ import annotations

import random
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import music_auto_image as mai  # noqa: E402
from services import music_auto_run as ar  # noqa: E402
from services import music_where_image as mwi  # noqa: E402

WHERE = "rooftop_music"


# ── A 회차 ────────────────────────────────────────────────────────────
def test_where_default_hours_8_21():
    assert ar.normalize_hours(None, ar.CHANNEL_DEFAULT_HOURS[WHERE]) == [8, 21]
    assert ar.normalize_hours([9, 22], ar.CHANNEL_DEFAULT_HOURS[WHERE]) == [9, 22]
    assert ar.normalize_hours(None) == [6, 18]                      # 운동 기본 그대로
    rs = ar.rounds_for_day(WHERE, date(2026, 10, 18), [8, 21], 2)
    assert [r["publish_at"].hour for r in rs] == [8, 21]
    assert all(0 <= r["publish_at"].minute <= 59 and r["publish_at"] - r["start_at"] == timedelta(minutes=120) for r in rs)


def test_busy_waits_until_T(monkeypatch):
    """운동 회차가 돌고 있으면 where 는 T 까지 기다렸다가 실행(동시 1개 락)."""
    from services import music_jobs, music_manual
    monkeypatch.setattr(music_jobs, "merge_metadata", lambda *a, **k: None)
    monkeypatch.setattr(music_jobs, "list_recent_by_type", lambda *a, **k: [])
    r = ar.rounds_for_day(WHERE, date.today() + timedelta(days=1), [8, 21], 2)[0]
    tries = {"n": 0}

    def _start(mood, tc, combo, *, channel=None, auto_image=None):
        tries["n"] += 1
        if tries["n"] <= 40:                                          # 80분 동안 busy(옛 상한 60분 초과)
            return {"ok": False, "error": "busy"}
        music_manual._JOBS["jw"] = {"status": "done", "mix_id": "m", "video_url": "https://x", "frame_thumb_key": "f"}
        return {"ok": True, "job_id": "jw"}
    monkeypatch.setattr(music_manual, "start", _start)
    monkeypatch.setattr(music_manual, "run", lambda jid: None)
    slept = []
    assert ar._produce(r, {"track_count": 10}, sleep=slept.append) == "m"
    assert len(slept) == 40


# ── B 장르 ────────────────────────────────────────────────────────────
def test_where_genres_are_15_without_excluded():
    assert len(mwi.WHERE_GENRES) == 15
    assert not {"workout", "hiphop", "kpop", "pop"} & set(mwi.WHERE_GENRES)


def test_genre_pick_uniform_and_no_three_in_a_row(monkeypatch):
    from services import music_jobs
    history: list[str] = []
    monkeypatch.setattr(music_jobs, "list_recent_by_type",
                        lambda t, ch, limit=2: [{"metadata": {"genre": g}} for g in reversed(history[-limit:])])
    rng = random.Random(7)
    for _ in range(30):
        history.append(ar.pick_where_genre(WHERE, rng=rng))
    assert all(not (a == b == c) for a, b, c in zip(history, history[1:], history[2:]))
    assert len(set(history)) >= 10                                   # 30회에 15개 중 대부분 등장(균등)
    # 강제로 직전 2회가 같으면 그 장르는 절대 안 나온다
    history[:] = ["jazz", "jazz"]
    assert all(ar.pick_where_genre(WHERE, rng=random.Random(i)) != "jazz" for i in range(200))


def test_where_round_passes_genre_as_mood(monkeypatch):
    from services import music_jobs, music_manual
    meta = {}
    monkeypatch.setattr(music_jobs, "merge_metadata", lambda jid, m: meta.update(m))
    monkeypatch.setattr(music_jobs, "list_recent_by_type", lambda *a, **k: [])
    got = {}

    def _start(mood, tc, combo, *, channel=None, auto_image=None):
        got.update(mood=mood, channel=channel, auto_image=auto_image, combo=combo, tc=tc)
        music_manual._JOBS["jw"] = {"status": "done", "mix_id": "m", "video_url": "https://x", "frame_thumb_key": "f"}
        return {"ok": True, "job_id": "jw"}
    monkeypatch.setattr(music_manual, "start", _start)
    monkeypatch.setattr(music_manual, "run", lambda jid: None)
    r = ar.rounds_for_day(WHERE, date(2026, 10, 18), [8, 21], 2)[0]
    ar._produce(r, {"track_count": 10}, sleep=lambda s: None)
    assert got["mood"] in mwi.WHERE_GENRES and got["channel"] == WHERE and got["auto_image"] is True
    assert got["combo"] is None and got["tc"] == 10 and meta["genre"] == got["mood"]


def test_workout_round_unchanged(monkeypatch):
    from services import music_jobs, music_manual
    monkeypatch.setattr(music_jobs, "merge_metadata", lambda *a, **k: None)
    got = {}

    def _start(mood, tc, combo, *, channel=None, auto_image=None):
        got.update(mood=mood, channel=channel)
        music_manual._JOBS["jw"] = {"status": "done", "mix_id": "m", "video_url": "https://x", "frame_thumb_key": "f"}
        return {"ok": True, "job_id": "jw"}
    monkeypatch.setattr(music_manual, "start", _start)
    monkeypatch.setattr(music_manual, "run", lambda jid: None)
    ar._produce(ar.rounds_for_day("workout_music", date(2026, 10, 18), [6, 18], 2)[0], {"track_count": 10}, sleep=lambda s: None)
    assert got == {"mood": None, "channel": "workout_music"}


def test_where_auto_theme_carries_genre_id_manual_does_not():
    from services import music_manual
    t = music_manual._build_theme("lofi", 10, channel=WHERE)
    assert t["genre_id"] == "lofi" and t["channel"] == WHERE
    assert "genre_id" not in music_manual._build_theme("lofi", 10, channel=None)   # where 수동 화면 그대로


# ── C 이미지 ─────────────────────────────────────────────────────────
def test_where_image_profile_and_prompt(monkeypatch):
    make, system, axis = mai._profile(None, WHERE, "lofi")
    p = make(["간판 문구"])
    assert system == mwi.REVIEW_SYSTEM and axis == "where/lofi"
    assert "도서관" in p or "책상" in p or "열람실" in p or "독서" in p
    assert "실존하는 특정 랜드마크" in p and "이번엔 반드시 피할 것" in p and "간판 문구" in p
    # 운동 프로필은 그대로(검수 None=운동 _REVIEW_SYSTEM, 축=strength)
    make_w, system_w, axis_w = mai._profile("workout", "workout_music", None)
    assert system_w is None and axis_w == "strength"
    make_n, system_n, axis_n = mai._profile("workout", None, "lofi")   # 채널 미지정 = 운동(기존 호출부)
    assert system_n is None and axis_n == "strength"


def test_where_person_rate_about_30pct():
    rng = random.Random(1)
    n = sum(mwi._PERSON_LINE in mwi.build_prompt("citypop", rng=rng) for _ in range(1000))
    assert 250 <= n <= 350


def test_where_review_criteria():
    r = mwi.REVIEW_SYSTEM
    for phrase in ("간판", "랜드마크", "비틀린 직선", "녹아내린 구조물", "HDR", "얼굴 정면 클로즈업", "자연 풍경 위주", "중앙이 하얗게"):
        assert phrase in r, phrase


def test_where_generate_uses_where_review_and_archive_keys(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(mai, "generate_image", lambda prompt, path: seen.setdefault("prompt", prompt) and Path(path).write_bytes(b"x") and {})
    monkeypatch.setattr(mai, "review_image", lambda path, system=None: seen.update(system=system) or {"pass": True, "reasons": []})
    res = mai.generate_reviewed(None, str(tmp_path / "bg.png"), channel=WHERE, genre="jazz")
    assert res["ok"] and seen["system"] == mwi.REVIEW_SYSTEM
    assert mai._archive_dir("where/jazz") == "music-auto-bg/where/jazz/"
    assert mai._last_key("where/jazz") == "music-auto-bg/_last_where_jazz.txt"
    assert mai._last_key("strength") == "music-auto-bg/_last_strength.txt"          # 운동 키 그대로


def test_where_image_constants_do_not_touch_manual_where():
    """where 수동 경로 상수는 이 모듈과 독립 — 같은 객체·내용을 공유하지 않는다."""
    from services import music_image_prompts as mip
    assert mwi.WHERE_TONE not in getattr(mip, "IMAGE_PROMPT_PREFIX", "")
    assert mwi.REVIEW_SYSTEM != mai._REVIEW_SYSTEM


# ── D 해시태그 ───────────────────────────────────────────────────────
@pytest.mark.parametrize("gid", sorted(mwi.WHERE_GENRES))
def test_where_hashtags_by_genre(gid):
    from services import music_translate
    tags = music_translate.generate_hashtags({"slug": "s", "genre_id": gid, "channel": WHERE},
                                             {"location_en": "Cozy Cafe", "mood_category": "chill"})
    en, ko = music_translate._WHERE_GENRE_TAGS[gid]
    assert tags[0] == "#playlist" and f"#{en[0]}" in tags and f"#{ko[0]}" in tags and "#CozyCafe" in tags
    assert 9 <= len(tags) <= 15 and len(tags) == len(set(tags))
    assert "#studymusic" not in tags or gid in ("sleep_study", "library_study")   # 고정 11개 제거


def test_where_hashtags_classify_from_label_when_no_genre_id():
    from services import music_translate
    tags = music_translate.generate_hashtags({"slug": "s", "genre": "재즈", "mood": "세련된"}, {})
    assert "#jazz" in tags and "#lofi" not in tags


def test_workout_hashtags_unchanged():
    from services import music_meta, music_translate
    th = {"slug": "s", "channel": "workout_music", "tag_combo": {"action": "workout", "genre": ["hiphop"]}}
    assert music_translate.generate_hashtags(th, {}) == music_meta.build_hashtags(th, {})


# ── E 제목 한국어 검증 ──────────────────────────────────────────────────
@pytest.mark.parametrize("i", range(20))
def test_title_korean_validation(monkeypatch, i):
    from services import music_lyrics, music_meta
    rng = random.Random(i)
    bad = ["Late Night Drive | city pop", "lofi beats | for study", "NoPipeLine", "  | empty"]
    good = "비 오는 밤의 재즈 | rainy night jazz"
    seq = [rng.choice(bad), good if rng.random() < 0.5 else rng.choice(bad)]
    calls = []
    monkeypatch.setattr(music_lyrics, "_call", lambda sys_, user, max_tokens=100: calls.append(1) or seq[len(calls) - 1])
    ko, en = music_meta._generate_title_copy({"slug": f"s{i}", "genre": "재즈", "mood": "세련된"}, {})
    assert music_meta._has_hangul(ko) and len(calls) == 2          # 1회 재생성까지만
    if seq[1] == good:
        assert ko == "비 오는 밤의 재즈"
    title = music_meta.build_title({"slug": f"s{i}", "genre": "재즈"}, {})
    assert music_meta._has_hangul(title.split("|")[0])


def test_title_tag_path_korean_validation(monkeypatch):
    from services import music_lyrics, music_meta
    seq = ["English Only | english", "운동할 때 듣는 힙합 | workout hip hop"]
    monkeypatch.setattr(music_lyrics, "_call", lambda *a, **k: seq.pop(0))
    ko, en = music_meta._generate_title_copy_tag({"tag_combo": {"action": "workout", "genre": ["hiphop"]}})
    assert ko == "운동할 때 듣는 힙합"
