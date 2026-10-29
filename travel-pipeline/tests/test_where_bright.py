"""where 배경 "청량 서울"(2026-10-29) + K-발라드 한국어 보컬."""

from __future__ import annotations

import random
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import music_auto_image as mai  # noqa: E402
from services import music_auto_run as ar  # noqa: E402
from services import music_song_lang as sl  # noqa: E402
from services import music_where_image as mwi  # noqa: E402


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("MUSIC_WHERE_STREET_RATE", "MUSIC_WHERE_BRIGHT_RATE", "MUSIC_LYRICS_KO_GENRES",
              "MUSIC_LYRICS_KO_ENABLED"):
        monkeypatch.delenv(k, raising=False)


def test_style_mix_default_70_15_15():
    r = random.Random(1)
    c = Counter(mwi.pick_style("cafe", rng=r) for _ in range(10000))
    assert abs(c["bright"] / 1e4 - 0.70) < 0.02
    assert abs(c["street"] / 1e4 - 0.15) < 0.02 and abs(c["space"] / 1e4 - 0.15) < 0.02
    r2 = random.Random(2)
    c2 = Counter(mwi.pick_style("lofi", rng=r2) for _ in range(10000))
    assert c2["street"] == 0 and abs(c2["bright"] / 1e4 - 0.70) < 0.02


def test_bright_rate_env(monkeypatch):
    monkeypatch.setenv("MUSIC_WHERE_BRIGHT_RATE", "1")
    assert mwi.pick_style("bar_lounge") == "bright"
    monkeypatch.setenv("MUSIC_WHERE_BRIGHT_RATE", "x")
    assert mwi.bright_rate() == 0.7


def test_every_where_genre_has_bright_scenes():
    for g in mwi.WHERE_GENRES:
        assert mwi.bright_scene_pool(g), g


def test_bright_prompt_is_bright_and_genre_matched():
    p = mwi.build_bright_prompt("breakup", ["중앙 과노출"], rng=random.Random(0))
    assert "파란 하늘" in p and "밤 장면 금지" in p and "한강" in p and "중앙 과노출" in p
    assert any(s in p for s in mwi._BRIGHT_SCENES["river"])
    lounge = mwi.build_bright_prompt("hotel_lobby", rng=random.Random(3))
    assert any(s in lounge for s in mwi._BRIGHT_SCENES["lounge"])
    assert "어둡거나 탁하다" in mwi.BRIGHT_REVIEW_SYSTEM


def test_profile_routes_bright_to_own_archive():
    make, review, axis = mai._profile(None, "rooftop_music", "cafe", style="bright")
    assert axis == "where-bright/cafe" and review is mwi.BRIGHT_REVIEW_SYSTEM
    assert "청량" in make([]) or "파란 하늘" in make([])


def test_bright_fallback_prefers_old_where_backgrounds(monkeypatch):
    calls = []
    monkeypatch.setattr(mai, "pick_reuse", lambda prefix, dest, **k: calls.append(prefix) or None)
    monkeypatch.setattr(mai, "pick_where_legacy", lambda dest: {"key": "old.png", "source": "where_legacy"})
    got = mai._bright_fallback("cafe", "/tmp/x.png")
    assert calls == ["where-bright"] and got["source"] == "where_legacy"


def test_ballad_is_always_korean_vocal():
    for i in range(50):
        assert sl.assign(3, rng=random.Random(i), genre_id="ballad") == ["ko"] * 3
    assert set(sl.assign(4, rng=random.Random(5), genre_id="citypop")) <= {"en", "inst"}
    assert sl.assign(2, lang="en", genre_id="ballad") == ["en", "en"]   # 보충(D)은 영상 언어 유지


def test_ko_genres_env(monkeypatch):
    assert sl.ko_genres() == {"ballad", "kcitypop"}
    monkeypatch.setenv("MUSIC_LYRICS_KO_GENRES", "none")
    assert sl.ko_genres() == frozenset()
    monkeypatch.setenv("MUSIC_LYRICS_KO_GENRES", "ballad, breakup")
    assert sl.ko_genres() == {"ballad", "breakup"}


def test_ballad_weighted_double(monkeypatch):
    from services import music_jobs
    monkeypatch.setattr(music_jobs, "list_recent_by_type", lambda *a, **k: [])
    r = random.Random(7)
    c = Counter(ar.pick_where_genre("rooftop_music", rng=r) for _ in range(16000))
    assert abs(c["ballad"] / 16000 - 2 / 17) < 0.012
    assert abs(c["jazz"] / 16000 - 1 / 17) < 0.01 and c["kcitypop"] > 0


def test_kcitypop_genre_korean_120bpm():
    from services import music_genres
    cfg = music_genres.suno_config("kcitypop")
    assert "118-122 BPM" in cfg["style"] and "korean city pop" in cfg["style"] and not cfg["instrumental"]
    assert music_genres.preset("kcitypop")["title_kr"] == "K-시티팝"
    assert sl.assign(2, rng=random.Random(1), genre_id="kcitypop") == ["ko", "ko"]
    assert "kcitypop" in mwi.WHERE_GENRES and mwi.bright_scene_pool("kcitypop")
    assert music_genres.classify("K-시티팝 플레이리스트") in ("kcitypop", "citypop")
