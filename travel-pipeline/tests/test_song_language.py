"""곡별 가사 언어(한 3 : 영 7) + 연주곡 혼합 — 결정 분포·연주곡 경로·보충(D)·제목 금지·언어 기록.

Suno·Claude 실호출 없음(전부 모킹).
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import music_song_lang as sl  # noqa: E402


@pytest.fixture(autouse=True)
def _rates(monkeypatch):
    monkeypatch.delenv("MUSIC_INSTRUMENTAL_RATE", raising=False)
    monkeypatch.delenv("MUSIC_LYRICS_EN_RATE", raising=False)
    monkeypatch.delenv("MUSIC_LYRICS_KO_ENABLED", raising=False)


# ── A 영상별 결정 분포(영상 하나는 한 가지로 통일) ─────────────────────────
def _videos(count=2000, n=10, seed=1):
    rng = random.Random(seed)
    return [sl.assign(n, rng=rng) for _ in range(count)]


def test_video_level_default_rates_no_korean():
    """2026-10-21 대표 결정: 기본은 한국어 0 — 영어 75 · 연주 25(두 채널 공통)."""
    vids = _videos()
    assert all(len(set(v)) == 1 and len(v) == 10 for v in vids)          # 영상 안에서는 섞지 않음
    c = Counter(v[0] for v in vids)
    assert c["ko"] == 0                                                  # 한국어 없음
    assert abs(c["en"] / 2000 - 0.75) < 0.03                             # 영어 75
    assert abs(c["inst"] / 2000 - 0.25) < 0.03                           # 연주 25


def test_korean_only_when_enabled(monkeypatch):
    monkeypatch.setenv("MUSIC_LYRICS_KO_ENABLED", "1")
    c = Counter(v[0] for v in _videos())
    assert abs(c["en"] / 2000 - 0.50) < 0.03                             # 허용 시 기존 50 · 25 · 25
    assert abs(c["ko"] / 2000 - 0.25) < 0.03
    assert abs(c["inst"] / 2000 - 0.25) < 0.03


def test_rates_follow_env(monkeypatch):
    monkeypatch.setenv("MUSIC_LYRICS_KO_ENABLED", "1")
    monkeypatch.setenv("MUSIC_INSTRUMENTAL_RATE", "0.5")
    monkeypatch.setenv("MUSIC_LYRICS_EN_RATE", "0.2")
    c = Counter(v[0] for v in _videos())
    assert abs(c["inst"] / 2000 - 0.5) < 0.04
    assert abs(c["en"] / (c["en"] + c["ko"]) - 0.20) < 0.04
    monkeypatch.setenv("MUSIC_INSTRUMENTAL_RATE", "0")
    monkeypatch.setenv("MUSIC_LYRICS_EN_RATE", "1")
    assert set(sl.assign(10)) == {"en"}
    monkeypatch.setenv("MUSIC_INSTRUMENTAL_RATE", "oops")                 # 잘못된 값 → 기본
    assert sl.instrumental_rate() == 0.25


def test_assign_fixed_lang_for_top_up():
    assert sl.assign(3, lang="ko") == ["ko", "ko", "ko"]
    assert sl.assign(2, lang="inst") == ["inst", "inst"]
    assert sl.assign(0) == []


# ── 제목 금지 패턴 ───────────────────────────────────────────────────
@pytest.mark.parametrize("t", ["A면", "B면", "Side A", "side b", "Track 1", "track no.3", "트랙 2",
                               "Intro", "Outro", "인트로", "아웃트로", "1번", "2 번 곡"])
def test_bad_titles(t):
    assert sl.is_bad_title(t)


@pytest.mark.parametrize("t", ["Midnight Drive", "새벽 세 시의 창문", "첫 번째 봄", "Abby면 돼", "Introvert Heart", "Outrun"])
def test_good_titles(t):
    assert not sl.is_bad_title(t)


def test_instrumental_style_drops_vocal_words():
    out = sl.instrumental_style("city pop, silky female vocals, warm synths, airy harmonies, 104 bpm")
    assert "vocal" not in out and "harmonies" not in out and out.endswith("instrumental") and "warm synths" in out


# ── produce(): 혼합 경로 ─────────────────────────────────────────────
@pytest.fixture
def env(monkeypatch):
    from services import music_lyrics, music_meta, music_produce, music_store, music_suno
    st = {"lyrics_calls": [], "suno": [], "inst_var": []}

    def _lyrics(theme, n, **k):
        st["lyrics_calls"].append({"n": n, "languages": k.get("languages")})
        langs = k.get("languages") or ["ko"] * n
        return [{"title": f"{lg}-{i}", "lyrics": f"lyrics {lg} {i}", "style": "pop, male vocals", "language": lg}
                for i, lg in enumerate(langs)]
    monkeypatch.setattr(music_lyrics, "generate_lyrics", _lyrics)

    def _gen(theme, **k):
        st["suno"].append(dict(theme))
        i = len(st["suno"])
        if i in st.get("fail", ()):
            raise RuntimeError("suno fail")
        return {"task_id": f"t{i}", "tracks": [{"audio_id": f"a{i}", "r2_key": f"k{i}"}, {"audio_id": f"b{i}", "r2_key": "x"}]}
    monkeypatch.setattr(music_suno, "generate_and_store", _gen)
    monkeypatch.setattr(music_store, "mark_track_used", lambda aid: True)
    monkeypatch.setattr(music_produce.r2_storage, "is_available", lambda: False)
    monkeypatch.setattr(music_produce, "_recycle_track", lambda *a, **k: pytest.fail("섞인 연주곡은 재활용 금지"))

    def _var(n, style, theme, *, en_rate=None):
        st["inst_var"].append({"n": n, "style": style, "en_rate": en_rate})
        return [{"title": f"Mood {i}", "style": f"{style}, var {i}"} for i in range(n)]
    monkeypatch.setattr(music_meta, "generate_instrumental_variations", _var)
    return music_produce, st


def test_mixed_video_instrumental_path(monkeypatch, env):
    mp, st = env
    from services import music_suno
    monkeypatch.setattr(sl, "assign", lambda n, rng=None: ["inst", "en", "ko", "inst", "en"][:n])
    events = []
    out = mp.produce("s", n=5, base_style="city pop, silky female vocals, warm synths",
                     do_master=False, do_mix=False, checkpoint=events.append)
    assert st["lyrics_calls"] == [{"n": 3, "languages": ["en", "ko", "en"]}]     # 연주곡 가사 호출 0
    assert [t["language"] for t in out["produced"]] == ["inst", "en", "ko", "inst", "en"]  # 위치 그대로
    inst = [t for t in st["suno"] if t["instrumental"]]
    assert len(inst) == 2 and all(t["language"] == "inst" and not t.get("lyrics") for t in inst)
    assert all("vocal" not in t["style"] for t in inst) and inst[0]["title"] == "Mood 0"   # 무드형 제목
    body = music_suno._build_body(inst[0])
    assert body["instrumental"] is True and "prompt" not in body and body["title"] == "Mood 0"
    assert st["inst_var"][0]["en_rate"] is None                            # 연주 제목은 기존 연주 영상 규칙
    vocal = [t for t in st["suno"] if not t["instrumental"]]
    assert [t["language"] for t in vocal] == ["en", "ko", "en"]
    assert all(e["record"].get("language") is None for e in events if e["type"] == "track")  # stub 레코드엔 없음
    assert len(st["suno"]) == 5                                              # 곡 수 = Suno 호출 수(2클립 중 1)


def test_all_instrumental_assignment_skips_lyrics(monkeypatch, env):
    mp, st = env
    monkeypatch.setattr(sl, "assign", lambda n, rng=None: ["inst"] * n)
    out = mp.produce("s", n=2, do_master=False, do_mix=False)
    assert st["lyrics_calls"] == [] and len(out["produced"]) == 2 and all(t["instrumental"] for t in st["suno"])


def test_top_up_uses_same_rule(monkeypatch, env):
    """복구 D — 모자란 곡 수만큼, 처음 정한 영상 언어 그대로 보충."""
    mp, st = env
    asked = []
    real = sl.assign

    def _spy(n, rng=None, lang=None):
        asked.append((n, lang))
        return real(n, rng=random.Random(n), lang=lang) if lang else ["en"] * n
    monkeypatch.setattr(sl, "assign", _spy)
    st["fail"] = {1, 2, 3}
    out = mp.produce("s", n=10, do_master=False, do_mix=False)
    assert asked == [(10, None), (3, "en")] and len(out["produced"]) == 10
    assert len(st["suno"]) == 13


def test_given_lyrics_and_instrumental_genre_unchanged(monkeypatch, env):
    """검수본 가사를 넘긴 경로·원래 연주인 장르는 혼합하지 않는다(기존 그대로)."""
    mp, st = env
    monkeypatch.setattr(sl, "assign", lambda *a, **k: pytest.fail("혼합하면 안 됨"))
    out = mp.produce("s", n=2, lyrics=[{"title": "t", "lyrics": "가사"}, {"title": "u", "lyrics": "가사2"}],
                     do_master=False, do_mix=False)
    assert all(not t["instrumental"] and t["language"] == "ko" for t in st["suno"]) and len(out["produced"]) == 2
    st["suno"].clear()
    from services import music_produce
    monkeypatch.setattr(music_produce, "_recycle_track", lambda *a, **k: None)   # 연주 장르는 재활용 기존대로
    mp.produce("s", n=2, genre_id="hotel_lobby", do_master=False, do_mix=False)
    assert all(t["instrumental"] for t in st["suno"])


def test_manual_and_auto_paths_reach_mixing(monkeypatch):
    """수동 "곡 만들기"·자동 회차(같은 music_manual.run)는 produce 에 가사를 넘기지 않는다 → 혼합 규칙 적용."""
    from services import music_jobs, music_manual, music_produce
    for name in ("fail_job", "update_job_step", "touch", "merge_metadata"):
        monkeypatch.setattr(music_jobs, name, lambda *a, **k: None)
    monkeypatch.setattr(music_jobs, "start_job", lambda *a, **k: k.get("job_id"))
    seen = []
    monkeypatch.setattr(music_produce, "produce", lambda slug, **k: seen.append(k) or (_ for _ in ()).throw(RuntimeError("stop")))
    for ch in (None, "workout_music", "rooftop_music"):
        jid = music_manual.start("jazz", 3, None, channel=ch, auto_image=False)["job_id"]
        music_manual.run(jid)
    assert len(seen) == 3 and all("lyrics" not in k for k in seen)


# ── B 영어 가사 프롬프트 ───────────────────────────────────────────────
def test_generate_lyrics_by_language(monkeypatch):
    from services import music_lyrics
    monkeypatch.setattr(music_lyrics, "is_available", lambda: True)
    calls = []

    def _call(system, user, **k):
        calls.append({"system": system, "user": user, "task": k.get("task")})
        if k.get("task") == "lyrics_plan":
            take = int(re.search(r"곡 수: (\d+)", user).group(1))
            tag = "EN" if "영어 곡을 기획" in system else "KO"
            return json.dumps([{"sub_theme": f"{tag}{i}", "title": f"{tag} title {i}", "style": "pop"} for i in range(take)])
        if k.get("task") == "lyrics_review":
            return json.dumps({"scores": {"depth": 9, "resonance": 9, "monotony": 9, "cliche": 9}, "lyrics": "final"})
        return "[Verse]\nline"
    monkeypatch.setattr(music_lyrics, "_call", _call)
    songs = music_lyrics.generate_lyrics("city pop", 4, languages=["en", "ko", "en", "en"])
    assert [s["language"] for s in songs] == ["en", "ko", "en", "en"]
    assert [s["sub_theme"] for s in songs] == ["EN0", "KO0", "EN1", "EN2"]
    plans = [c for c in calls if c["task"] == "lyrics_plan"]
    assert len(plans) == 2 and "한국어 기반 + 영어 훅 살짝" in plans[0]["user"]          # 한국어 규칙 그대로
    assert "번역투" in plans[1]["user"] and "KO0 / KO title 0" in plans[1]["user"]       # 영어 플랜은 한국어 주제 회피
    writes = [c for c in calls if c["task"] == "lyrics_write"]
    assert sum("영어권 네이티브 작사가" in w["system"] for w in writes) == 3
    assert sum("너는 한국어 작사가다" in w["system"] for w in writes) == 1
    reviews = [c for c in calls if c["task"] == "lyrics_review"]
    assert sum("영어로 유지" in r["user"] for r in reviews) == 3
    assert all(sl.TITLE_RULE in p["user"] for p in plans)                                 # 금지 패턴 지시


def test_bad_plan_title_is_regenerated_once(monkeypatch):
    from services import music_lyrics
    seq = iter(["Side B", "새벽 버스"])

    def _call(system, user, **k):
        if k.get("task") == "lyrics_plan":
            return json.dumps([{"sub_theme": "a", "title": "A면"}, {"sub_theme": "b", "title": "Track 2"},
                               {"sub_theme": "c", "title": "괜찮은 제목"}])
        return next(seq)
    monkeypatch.setattr(music_lyrics, "_call", _call)
    plans = music_lyrics.plan_songs("x", 3)
    assert [p["title"] for p in plans] == ["", "새벽 버스", "괜찮은 제목"]      # 또 걸리면 빈 제목(Suno 자동)


def test_instrumental_variation_bad_titles_removed(monkeypatch):
    from services import music_lyrics, music_meta
    monkeypatch.setattr(music_lyrics, "is_available", lambda: True)
    got = {}

    def _call(system, user, **k):
        got["system"], got["user"] = system, user
        return "Intro | soft piano\n고요한 새벽 | warm keys\nSide A | lofi beat"
    monkeypatch.setattr(music_lyrics, "_call", _call)
    out = music_meta.generate_instrumental_variations(3, "piano", {}, en_rate=0.7)
    assert [o["title"] for o in out] == ["", "고요한 새벽", ""] and out[0]["style"] == "soft piano"
    assert "약 2곡은 영어" in got["user"] and sl.TITLE_RULE in got["system"]
    music_meta.generate_instrumental_variations(10, "piano", {})
    assert "약 2곡은 영어" in got["user"]                                       # 연주 영상은 기존 20%


# ── 언어 기록(music_tracks.language · 재취득 F) ──────────────────────────
def test_language_recorded_on_both_clips(monkeypatch):
    from services import music_store, music_suno
    rows = []
    monkeypatch.setattr(music_store, "upsert_track", lambda rec: rows.append(rec) or {"stored": True})
    monkeypatch.setattr(music_suno.r2_storage, "music_exists", lambda *a: True)
    music_suno.store_tracks("s", "t1", [{"audio_id": "a", "audio_url": "u"}, {"audio_id": "b", "audio_url": "v"}],
                            genre="jazz", language="en")
    assert [r["language"] for r in rows] == ["en", "en"]                     # 쌍둥이 2클립 같은 값
    rows.clear()
    music_suno.store_tracks("s", "t1", [{"audio_id": "a", "audio_url": "u"}])   # 콜백(언어 모름) → 키 생략
    assert "language" not in rows[0]
    sent = {}
    monkeypatch.setattr(music_suno, "submit_generation", lambda theme: "t9")
    monkeypatch.setattr(music_suno, "poll_task", lambda *a, **k: [])
    monkeypatch.setattr(music_suno, "store_with_retry", lambda *a, **k: sent.update(k) or [])
    music_suno.generate_and_store({"theme_slug": "s", "language": "inst"})
    assert sent["language"] == "inst"


def test_reacquire_and_checkpoint_keep_language(monkeypatch):
    from services import music_produce, music_recovery, music_suno
    got = {}
    monkeypatch.setattr(music_suno, "poll_task", lambda *a, **k: [])
    monkeypatch.setattr(music_suno, "store_with_retry", lambda *a, **k: got.update(k) or [])
    music_recovery.reacquire({"task_id": "t", "slug": "s", "language": "ko"})
    assert got["language"] == "ko"
    assert music_produce._track_brief({"audio_id": "a", "language": "en"})["language"] == "en"
    cp = music_recovery.Checkpoint("j", {})
    monkeypatch.setattr(cp, "save", lambda: None)
    cp({"type": "store_failed", "task_id": "t", "language": "inst"})
    assert cp.pending[0]["language"] == "inst"


# ── 영상 제목·원본 언어 ─────────────────────────────────────────────────
@pytest.mark.parametrize("i", range(20))
def test_video_title_hangul_first_with_english_songs(monkeypatch, i):
    from services import music_lyrics, music_meta
    rng = random.Random(i)
    replies = ["Late Night Drive | city pop", "비 오는 밤의 재즈 | rainy night jazz", "Only English | x"]
    monkeypatch.setattr(music_lyrics, "_call", lambda *a, **k: rng.choice(replies))
    theme = {"slug": f"s{i}", "genre": "재즈", "mood": "세련된", "title_kr": "재즈",
             "tracks": [{"title": "Midnight Drive", "language": "en"}]}
    title = music_meta.build_title(theme, {})
    assert re.match(r"^[가-힣]", title.removeprefix("playlist🎧 ")), title


def test_meta_source_lang_is_title_based():
    from services import music_translate as mt
    assert mt.detect_meta_lang({"title_kr": "새벽 드라이브"}) == "ko"
    assert mt.detect_meta_lang({"title_kr": ""}) == "ko" and mt.detect_meta_lang(None) == "ko"
    # 가사가 전부 영어여도 메타 원본은 제목 기준 ko(가사 번역 원본 판정은 그대로)
    assert mt.detect_source_lang("all english lyrics") == "en"
    src = Path(mt.__file__).read_text(encoding="utf-8")
    assert "src = detect_meta_lang(theme)" in src
