"""검색 키워드 풀 — 수집·점수화·고유명사 필터·제목·해시태그·태그·쿼터 로그(외부 API 실호출 없음)."""

from __future__ import annotations

import json
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import music_keyword_pool as kp  # noqa: E402
from test_workout_image_reuse import _FakeS3  # noqa: E402

KST = kp.KST
NOW = datetime(2026, 10, 20, 3, 12, tzinfo=KST)


def _v(i, title, channel, views=100_000, tags=(), days=10, desc=""):
    return {"id": f"v{i}", "title": title, "channel": channel, "views": views, "tags": list(tags),
            "description": desc, "published_at": (NOW - timedelta(days=days)).astimezone(timezone.utc).isoformat()}


# ── 수집(HTTP 모킹) ──────────────────────────────────────────────────
class _Client:
    def __init__(self, per_query=3):
        self.calls: list[tuple[str, dict]] = []
        self.per_query = per_query

    def get(self, url, params=None):
        self.calls.append((url, dict(params or {})))
        if url.endswith("/search"):
            q = params["q"]
            items = [{"id": {"videoId": f"{q}-{i}"}} for i in range(self.per_query)]
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"items": items})
        ids = params["id"].split(",")
        items = [{"id": vid, "snippet": {"title": f"운동할 때 듣는 노래 {vid}", "tags": ["헬스 노래"],
                                        "channelTitle": f"ch{n}", "publishedAt": "2026-10-01T00:00:00Z",
                                        "description": "#운동플리"},
                  "statistics": {"viewCount": str(10_000 * (n + 1))}} for n, vid in enumerate(ids)]
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"items": items})


def test_search_params():
    c = _Client()
    out = kp.search("헬스 노래", key="K", now=NOW, client=c)
    url, p = c.calls[0]
    assert url.endswith("/search") and p["order"] == "viewCount" and p["maxResults"] == 50
    assert p["regionCode"] == "KR" and p["relevanceLanguage"] == "ko" and p["videoDuration"] == "long"
    assert p["publishedAfter"] == "2026-07-21T18:12:00Z"                          # 최근 90일
    assert c.calls[1][1]["part"] == "snippet,statistics" and len(out) == 3 and out[0]["views"] == 10_000
    kp.search("gym motivation music", key="K", now=NOW, client=c)
    assert "relevanceLanguage" not in c.calls[2][1]                               # 영어 검색어는 언어 제한 없음


def test_daily_queries_and_quota():
    q = kp.daily_queries(NOW)
    assert len(q[kp.WORKOUT]) == 7 and len(q[kp.WHERE]) == 11
    genres = [g for _, g in q[kp.WHERE] if g]
    assert len(genres) == 3 and all(g in kp.WHERE_GENRE_QUERIES for g in genres)
    nxt = [g for _, g in kp.daily_queries(NOW + timedelta(days=1))[kp.WHERE] if g]
    assert set(genres) != set(nxt)                                                # 장르 순환
    seen = set()
    for d in range(5):
        seen |= {g for _, g in kp.daily_queries(NOW + timedelta(days=d))[kp.WHERE] if g}
    assert seen == set(kp.WHERE_GENRE_QUERIES)                                    # 5일에 15장르 전부
    assert kp.quota_units(1, 50) == 101 and kp.quota_units(18, 18 * 50) == 18 * 100 + 18


@pytest.fixture
def s3(monkeypatch):
    from adapters import r2_storage
    fake = _FakeS3()
    monkeypatch.setattr(r2_storage, "_get_client", lambda: fake)
    monkeypatch.setattr(kp, "_cache", {})
    return fake


def test_run_daily_skips_without_dedicated_key(monkeypatch, s3, caplog):
    monkeypatch.delenv("MUSIC_TREND_YOUTUBE_API_KEY", raising=False)
    monkeypatch.setenv("YOUTUBE_API_KEY", "upload-quota-key")                     # 있어도 쓰지 않는다
    c = _Client()
    assert kp.run_daily(NOW, client=c) == {"skipped": "no_key"}
    assert c.calls == [] and any("건너뜀" in r.getMessage() for r in caplog.records)


def test_run_daily_collects_and_saves(monkeypatch, s3):
    from services import music_lyrics, music_trend
    monkeypatch.setenv("MUSIC_TREND_YOUTUBE_API_KEY", "K")
    monkeypatch.setattr(music_lyrics, "_call", lambda *a, **k: '{"drop": []}')
    saved = []
    monkeypatch.setattr(music_trend, "save_insight", lambda ins: saved.append(ins) or {"stored": True})
    c = _Client(per_query=4)
    out = kp.run_daily(NOW, client=c)
    assert out["searches"] == 18 and out["units"] == 18 * 101                     # 하루 약 1,818 units
    assert all(p.get("key") == "K" for _, p in c.calls)
    pool = json.loads(s3.objs["music-trends/pool_workout_music.json"][0])
    assert pool["ko"] and all(x["channels"] >= 3 for x in pool["ko"])
    assert [x["score"] for x in pool["ko"]] == sorted((x["score"] for x in pool["ko"]), reverse=True)
    where = json.loads(s3.objs["music-trends/pool_rooftop_music.json"][0])
    assert len(where["genres"]) == 3
    assert saved and saved[0]["summary"].startswith("검색 키워드 상위") and saved[0]["mood_keywords"]


# ── 점수화 · 고유명사 필터 ─────────────────────────────────────────────
def _fixture_videos():
    vids = []
    for i, ch in enumerate(["헬스뮤직", "GymTV", "런닝플리", "운동채널"]):
        vids.append(_v(i, f"[{ch}] 헬스장 텐션 올리는 운동할 때 듣는 노래 2024 | Workout Music Playlist", ch,
                       views=1_000_000 // (i + 1), tags=["헬스 노래", "workout music"], desc="#운동플리 #헬스노래"))
    vids += [
        _v(10, "아이유 - 좋은날 (Official MV) 운동할 때 듣는 노래", "아이유 공식", 9_000_000),
        _v(11, "NewJeans 'Super Shy' 1시간 반복 헬스 노래", "뉴진스팬", 5_000_000),
        _v(12, "Cover 커버 플레이리스트 | 헬스장 플레이리스트", "커버맨", 50_000),
        _v(13, "헬스장 플레이리스트 오직 두 채널만", "커버맨2", 50_000),
    ]
    return vids


def test_scoring_and_rule_filters():
    items = kp.score(_fixture_videos(), NOW)
    kws = [x["kw"] for x in items]
    assert "운동할 때 듣는 노래" in kws and "헬스 노래" in kws and "Workout Music Playlist" in kws
    joined = " ".join(kws)
    for bad in ("아이유", "좋은날", "NewJeans", "Super Shy", "헬스뮤직", "GymTV", "2024", "1시간", "Official"):
        assert bad not in joined, bad                                             # 가수·곡·채널·숫자 제거
    assert "헬스장 플레이리스트" not in kws                                        # 2개 채널뿐 → 탈락
    assert all(x["channels"] >= 3 for x in items)
    assert items == sorted(items, key=lambda x: (-x["score"], x["kw"]))
    assert {"ko", "en"} >= {x["lang"] for x in items}


def test_recency_and_views_weight():
    fresh = [_v(i, "운동할 때 듣는 노래", f"c{i}", views=100_000, days=1) for i in range(3)]
    old = [_v(10 + i, "헬스 노래", f"c{i}", views=100_000, days=89) for i in range(3)]
    s = {x["kw"]: x["score"] for x in kp.score(fresh + old, NOW)}
    assert s["운동할 때 듣는 노래"] > s["헬스 노래"]


def test_llm_proper_noun_check(monkeypatch):
    from services import music_lyrics
    items = [{"kw": "헬스 노래", "score": 9, "channels": 3, "lang": "ko"},
             {"kw": "블랙핑크 운동", "score": 8, "channels": 3, "lang": "ko"},
             {"kw": "workout music", "score": 7, "channels": 3, "lang": "en"}]
    monkeypatch.setattr(music_lyrics, "_call", lambda *a, **k: '{"drop": [1]}')
    assert [x["kw"] for x in kp.llm_drop_proper_nouns(items)] == ["헬스 노래", "workout music"]
    monkeypatch.setattr(music_lyrics, "_call", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert kp.llm_drop_proper_nouns(items) == items                                # 실패 → 규칙 필터만


# ── 제목 ─────────────────────────────────────────────────────────────
POOL = {
    kp.WORKOUT: {"ko": [{"kw": k, "score": 10 - i} for i, k in enumerate(
        ["운동할 때 듣는 노래", "헬스 노래", "헬스장 플레이리스트", "운동 플리", "러닝 플레이리스트", "운동 자극"])],
        "en": [{"kw": k, "score": 5 - i} for i, k in enumerate(["Workout Music Playlist", "Gym Motivation Music", "Running Music"])]},
    kp.WHERE: {"ko": [{"kw": k, "score": 9 - i} for i, k in enumerate(["카페 음악", "공부할 때 듣는 음악", "재즈 플레이리스트"])],
               "en": [{"kw": "Cafe Jazz", "score": 3}, {"kw": "Study Music", "score": 2}],
               "genres": {"jazz": {"ko": [{"kw": "재즈 플레이리스트", "score": 5}], "en": [{"kw": "Late Night Jazz", "score": 4}]}}},
}


@pytest.fixture
def pool(monkeypatch, s3):
    monkeypatch.setattr(kp, "get_pool", lambda ch: POOL.get(ch or kp.WHERE, {}))
    return s3


def _ko_part(title: str) -> str:
    return title.removeprefix("playlist🎧 ").split("|", 1)[0].strip()


@pytest.mark.parametrize("i", range(20))
def test_title_has_search_keyword_hangul_first_recent_avoid(monkeypatch, pool, i):
    from services import music_lyrics, music_meta, music_tags
    rng = random.Random(i)
    replies = [
        "헬스장 텐션 200% 올려주는 운동할 때 듣는 노래 | gym motivation music",   # 키워드 포함
        "마지막 세트까지 버티는 그 느낌 | push harder",                           # 키워드 없음 → 재생성
        "Only English | english",                                                 # 앞자리 한글 아님
        "숨차도 멈출 수 없는 러닝 플레이리스트 | 러닝 | Running Music |",           # 파이프 버그 형태
    ]
    calls = []
    monkeypatch.setattr(music_lyrics, "_call", lambda *a, **k: calls.append(a[1]) or rng.choice(replies))
    theme = {"slug": f"w{i}", "channel": kp.WORKOUT, "track_count": 10,
             "tag_combo": music_tags.smart_random({"action": "workout"}), "video_language": rng.choice(["ko", "en", "inst"])}
    title = music_meta.build_title(theme, {})
    ko = _ko_part(title)
    assert re.match(r"^[가-힣]", ko) and len(title) <= 100 and title.count("|") == 1, title
    assert any(re.sub(r"\s", "", k) in re.sub(r"\s", "", ko) for k in [x["kw"] for x in POOL[kp.WORKOUT]["ko"]]), title
    assert "[검색 키워드" in calls[0] and "최근 제목" in calls[0]
    # 다음 영상 프롬프트에는 방금 제목이 "최근 제목"으로 들어간다(겹침 회피)
    music_meta.build_title({**theme, "slug": f"w{i}-next"}, {})
    assert ko in calls[-1]


def test_keywords_order_recent_inst_lang(pool):
    ko, en = kp.keywords(kp.WORKOUT, recent=["헬스장 텐션 올려주는 운동할 때 듣는 노래 | x"])
    assert ko[0] == "헬스 노래" and ko[-1] == "운동할 때 듣는 노래"                  # 최근 쓴 키워드는 뒤로
    ko, en = kp.keywords(kp.WHERE, "jazz")
    assert ko[0] == "재즈 플레이리스트" and en[0] == "Late Night Jazz"              # 장르 풀 우선, 중복 없음
    assert len(ko) == len(set(ko))


def test_where_title_uses_genre_keywords(monkeypatch, pool):
    from services import music_lyrics, music_meta
    monkeypatch.setattr(music_lyrics, "_call", lambda *a, **k: "밤 11시 혼자 듣는 재즈 플레이리스트 | Late Night Jazz Playlist")
    t = music_meta.build_title({"slug": "h1", "channel": kp.WHERE, "genre_id": "jazz", "genre": "재즈"}, {})
    assert t == "playlist🎧 밤 11시 혼자 듣는 재즈 플레이리스트 | Late Night Jazz Playlist"


def test_title_fallback_hook_plus_keyword(monkeypatch, pool):
    from services import music_lyrics, music_meta
    monkeypatch.setattr(music_lyrics, "_call", lambda *a, **k: "키워드 없는 감성 제목 | no keyword here")
    ko, en = music_meta._generate_title_copy_tag({"slug": "z", "channel": kp.WORKOUT, "tag_combo": {"action": "workout"}})
    assert ko.endswith(POOL[kp.WORKOUT]["ko"][0]["kw"]) and en == "Workout Music Playlist"


def test_no_pool_keeps_old_title_path(monkeypatch, s3):
    from services import music_lyrics, music_meta
    monkeypatch.setattr(kp, "get_pool", lambda ch: {})
    calls = []
    monkeypatch.setattr(music_lyrics, "_call", lambda *a, **k: calls.append(a[1]) or "비 오는 밤의 재즈 | rainy night jazz")
    assert music_meta._generate_title_copy({"slug": "s", "genre": "재즈"}, {}) == ("비 오는 밤의 재즈", "rainy night jazz")
    assert "[검색 키워드" not in calls[0]


@pytest.mark.parametrize("raw,expected", [
    ("창문 열고 싶어지는 그 느낌 | 기분좋게 만들어주는 음악 | fresh morning drive beats |",
     ("창문 열고 싶어지는 그 느낌", "fresh morning drive beats")),
    ("비 오는 밤 | rainy night jazz", ("비 오는 밤", "rainy night jazz")),
    ("한국어 | 한국어만", None),
    ("English | only", None),
])
def test_pipe_bug_split(raw, expected):
    from services import music_meta
    assert music_meta._split_title_line(raw) == expected


# ── 해시태그 · 태그 ───────────────────────────────────────────────────
@pytest.mark.parametrize("lang,front", [
    ("ko", ["#운동할때듣는노래", "#헬스노래", "#WorkoutMusicPlaylist"]),
    ("en", ["#WorkoutMusicPlaylist", "#GymMotivationMusic", "#운동할때듣는노래"]),
])
def test_hashtags_front3_and_cap(pool, lang, front):
    from services import music_meta, music_translate
    th = {"slug": "s", "channel": kp.WORKOUT, "tag_combo": {"action": "workout", "genre": ["hiphop"]}, "video_language": lang}
    tags = music_meta.build_hashtags(th, {})
    assert tags[:3] == front and len(tags) <= 15 and len({t.lower() for t in tags}) == len(tags)
    assert music_translate.generate_hashtags(th, {}) == tags                     # 두 경로 같은 결과
    where = music_translate.generate_hashtags({"slug": "s", "channel": kp.WHERE, "genre_id": "jazz"}, {})
    assert where[:2] == ["#재즈플레이리스트", "#카페음악"] and len(where) <= 15


def test_hashtags_unchanged_without_pool(monkeypatch, s3):
    from services import music_meta
    monkeypatch.setattr(kp, "get_pool", lambda ch: {})
    th = {"slug": "s", "channel": kp.WORKOUT, "tag_combo": {"action": "workout", "genre": ["hiphop"]}}
    assert music_meta.build_hashtags(th, {}) == music_meta._build_hashtags_base(th, {})


def test_snippet_tags_limit_and_clean(monkeypatch, pool):
    from services import youtube_upload
    big = {"ko": [{"kw": f"운동할 때 듣는 노래 버전{i:02d}"} for i in range(40)], "en": [{"kw": "Workout Music Playlist"}]}
    monkeypatch.setattr(kp, "get_pool", lambda ch: big)
    theme = {"slug": "s", "channel": kp.WORKOUT, "genre": "hiphop", "situation": "workout", "mood": "workout",
             "style_prompt": "hard-hitting drums, punchy 808 bass, gritty texture"}
    _, _, tags = youtube_upload.build_music_metadata(theme, {"tracks": []})
    assert kp.tags_chars(tags) <= 500 and "Rooftop Music" not in tags
    assert not any("drums" in t or "808" in t for t in tags)                       # style 조각 없음
    monkeypatch.setattr(kp, "get_pool", lambda ch: POOL[kp.WORKOUT])
    _, _, tags = youtube_upload.build_music_metadata(theme, {"tracks": []})
    assert tags[0] == "운동할 때 듣는 노래" and "playlist" in tags


def test_tags_chars_counts_quotes():
    assert kp.tags_chars(["a b", "cd"]) == 3 + 2 + 2 + 1


# ── 쿼터 로그 ─────────────────────────────────────────────────────────
def test_upload_quota_log(caplog):
    from api.routes import music_dashboard as md
    ml = {"localizations": {"ok": True, "applied": ["en"], "failed": {}},
          "captions": {"uploaded": ["ko", "en"], "failed": {"ja": "quotaExceeded"}, "skipped": ["th"]}}
    with caplog.at_level("WARNING"):
        units = md._log_upload_quota("mix1", {"video_id": "v", "thumbnail_set": True, "playlist_added": False}, ml)
    assert units == 1 + 1600 + 50 + 0 + 50 + 400 * 3
    line = next(r.getMessage() for r in caplog.records if "[yt-quota]" in r.getMessage())
    assert "자막 성공 2 / 실패 1 / 건너뜀 1" in line and "ja(quotaExceeded)" in line
    assert md._log_upload_quota("m", {"video_id": "v"}, {"localizations": {"ok": False}, "captions": {}}) == 1601
