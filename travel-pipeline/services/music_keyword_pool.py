"""검색 키워드 풀(대표 승인 2026-10-20) — 경쟁 인기 플레이리스트 영상 → 채널(·장르)별 "실제 검색어" 풀.

목적: 제목·해시태그·태그에 사람들이 실제로 검색하는 말을 넣어, 경쟁 인기 영상의 관련·추천에 같이 뜨게.
트렌드 분석 정상화도 겸한다(기존 music_trend 는 영어 키워드 7개 혼합·기간 제한 없음·6월 이후 멈춤).

수집(매일 1회, 백엔드 스케줄러 03:12 KST — 외부 cron 불필요)
  - 운동 7개 + where 기본 8개 + where 장르 순환 3개 = 하루 18회 검색.
  - YouTube Data API: search.list(100 units, part=id, order=viewCount, 최근 90일, regionCode=KR,
    한글 검색어는 relevanceLanguage=ko, videoDuration=long, maxResults=50) + videos.list(1 unit / 50개).
    → 하루 약 18 × 101 = 1,818 units.
  - ⚠️ 검색 전용 키 MUSIC_TREND_YOUTUBE_API_KEY 가 **없으면 수집을 건너뛴다**(로그만). 업로드와 같은
    쿼터(YOUTUBE_API_KEY)를 쓰다 업로드가 실패하면 안 되기 때문(대표 지시).

점수화 · 고유명사 필터(0단계 승인 4)
  1) 규칙: 채널명·따옴표/대괄호 안·"MV/Official/feat/cover/가사/lyrics" 구절·숫자(연도·길이·곡수) 제거.
  2) 채널 교차: 서로 다른 채널 3곳 이상에 나온 구절만(고유명사는 한 채널에 몰린다).
  3) LLM 확인: 상위 40개 중 가수·곡·채널·브랜드명을 Claude 가 골라 뺀다(실패하면 1·2만).
  점수 = Σ log10(조회수+10) × 기간 가중(오늘 1.0 → 90일 0.5), 영상당 1번.

저장(SQL 없음): R2 음악 버킷 music-trends/pool_{채널}.json(+장르별 하위 풀), recent_titles_{채널}.json.
기존 music_trends 테이블에도 같은 형식으로 1행 — 주제 영감(music_theme)·썸네일 톤·대시보드 트렌드 패널이
그대로 최신 데이터를 본다.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
API = "https://www.googleapis.com/youtube/v3"
PREFIX = "music-trends"
WINDOW_DAYS = 90
MAX_RESULTS = 50
MIN_CHANNELS = 3
LLM_CHECK_TOP = 40
POOL_SIZE = 30
GENRE_ROTATE_PER_DAY = 3
SEARCH_UNITS = 100
VIDEOS_UNITS = 1
CACHE_SEC = 600.0
RECENT_TITLES = 20
TAGS_MAX_CHARS = 500
HASHTAG_MAX = 15

WORKOUT = "workout_music"
WHERE = "rooftop_music"

QUERIES: dict[str, list[str]] = {
    WORKOUT: [
        "운동할 때 듣는 노래", "헬스 노래", "헬스장 플레이리스트", "러닝 플레이리스트", "운동 플리",
        "workout music playlist", "gym motivation music",
    ],
    WHERE: [
        "카페 음악", "공부할 때 듣는 음악", "재즈 플레이리스트", "시티팝 플레이리스트", "드라이브 노래",
        "잠잘 때 듣는 음악", "lofi", "cafe jazz",
    ],
}

# where 장르 순환 검색어(하루 3개씩 돌아가며 장르별 하위 풀을 갱신 — 15장르 = 5일 주기).
WHERE_GENRE_QUERIES: dict[str, str] = {
    "citypop": "시티팝 플레이리스트", "sunset_drive": "드라이브 노래", "morning_drive": "출근길 노래",
    "cafe": "카페 음악", "jazz": "재즈 플레이리스트", "ballad": "발라드 플레이리스트",
    "breakup": "이별 노래 플레이리스트", "sleep_study": "잠잘 때 듣는 음악", "lofi": "lofi 플레이리스트",
    "rnb_soul": "알앤비 플레이리스트", "hotel_lobby": "호텔 라운지 음악", "cafe_bgm": "카페 브금",
    "bar_lounge": "바 재즈 플레이리스트", "spa_meditation": "명상 음악", "library_study": "공부할 때 듣는 음악",
}

_HANGUL = re.compile(r"[가-힣]")
_DIGIT = re.compile(r"\d")
_QUOTED = re.compile(r"[\[【「『\"“‘][^\]】」』\"”’]{0,60}[\]】」』\"”’]")
_SPLIT = re.compile(r"[|·•\-–—/:!?,~♪♬🎧🎵🎶❤♡☕️🔥✨💪🏃]+|\s{2,}")
_BAD = re.compile(r"\b(mv|m/v|official|feat\.?|ft\.?|cover|remix|live|lyrics?|teaser|ost)\b|커버|가사|뮤비|뮤직비디오|직캠",
                  re.IGNORECASE)
_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿]")
# 단독으로는 검색어가 아닌 일반어(구절 안에서는 허용).
_GENERIC = {
    "music", "playlist", "playlists", "mix", "best", "top", "songs", "song", "the", "for", "and", "of", "to",
    "노래", "음악", "플리", "플레이리스트", "모음", "bgm", "브금", "광고없는", "광고없음", "hours", "hour",
}

_LOCK = threading.Lock()
_cache: dict[str, tuple[float, dict]] = {}


# ── 키 · 쿼터 ─────────────────────────────────────────────────────────
def api_key() -> str:
    """검색 전용 키만 쓴다 — 없으면 "" (수집 건너뜀). 업로드 쿼터(YOUTUBE_API_KEY)로 폴백하지 않는다."""
    return (os.getenv("MUSIC_TREND_YOUTUBE_API_KEY") or "").strip()


def daily_queries(day: datetime | None = None) -> dict[str, list[tuple[str, str | None]]]:
    """채널 → [(검색어, 장르 또는 None)]. where 는 기본 8개 + 장르 순환 3개."""
    d = (day or datetime.now(KST)).astimezone(KST).date()
    genres = sorted(WHERE_GENRE_QUERIES)
    start = (d.toordinal() * GENRE_ROTATE_PER_DAY) % len(genres)
    rot = [genres[(start + i) % len(genres)] for i in range(GENRE_ROTATE_PER_DAY)]
    return {
        WORKOUT: [(q, None) for q in QUERIES[WORKOUT]],
        WHERE: [(q, None) for q in QUERIES[WHERE]] + [(WHERE_GENRE_QUERIES[g], g) for g in rot],
    }


def quota_units(n_searches: int, n_videos: int) -> int:
    """search.list 100 × 검색 수 + videos.list 1 × ceil(영상 수 / 50)(검색 1번에 최대 50개라 보통 검색당 1)."""
    return n_searches * SEARCH_UNITS + math.ceil(n_videos / 50) * VIDEOS_UNITS


# ── 수집 ─────────────────────────────────────────────────────────────
def search(query: str, *, key: str, now: datetime, client: httpx.Client | None = None) -> list[dict]:
    """검색어 1개 → 영상 메타(title·tags·description·channel·views·published). 실패는 예외."""
    after = (now - timedelta(days=WINDOW_DAYS)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {"part": "id", "q": query, "type": "video", "order": "viewCount", "maxResults": MAX_RESULTS,
              "publishedAfter": after, "regionCode": "KR", "videoDuration": "long", "key": key}
    if _HANGUL.search(query):
        params["relevanceLanguage"] = "ko"
    own = client is None
    c = client or httpx.Client(timeout=20.0)
    try:
        r = c.get(f"{API}/search", params=params)
        r.raise_for_status()
        ids = [it["id"]["videoId"] for it in r.json().get("items", []) if (it.get("id") or {}).get("videoId")]
        if not ids:
            return []
        r = c.get(f"{API}/videos", params={"part": "snippet,statistics", "id": ",".join(ids[:50]), "key": key})
        r.raise_for_status()
        out = []
        for it in r.json().get("items", []):
            sn, stt = it.get("snippet") or {}, it.get("statistics") or {}
            out.append({
                "id": it.get("id"), "title": sn.get("title") or "", "tags": sn.get("tags") or [],
                "description": (sn.get("description") or "")[:2000], "channel": sn.get("channelTitle") or "",
                "views": int(stt.get("viewCount") or 0), "published_at": sn.get("publishedAt") or "",
                "query": query,
            })
        return out
    finally:
        if own:
            c.close()


# ── 구절 추출 · 규칙 필터 ─────────────────────────────────────────────
def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def _key(s: str) -> str:
    return re.sub(r"\s+", "", norm(s))


def _ok_phrase(p: str, channel_keys: set[str]) -> bool:
    p = p.strip()
    k = _key(p)
    if len(k) < 2 or len(p) > 30 or _DIGIT.search(p) or _BAD.search(p) or _EMOJI.search(p):
        return False
    if not _HANGUL.search(p) and len(k) < 4:
        return False
    if k in {_key(g) for g in _GENERIC}:
        return False
    if any(ck and (ck == k or (len(ck) >= 3 and ck in k)) for ck in channel_keys):
        return False
    return True


# n-gram 이 꾸밈말로 끝나면("…운동할", "…듣는") 문장 조각이라 키워드가 아니다.
_DANGLING = re.compile(r"[가-힣](?:는|할|을|던|의|를|에|고)$")


def phrases_of(video: dict, channel_keys: set[str]) -> set[str]:
    """영상 1개 → 후보 구절(제목 조각·2~4어절 n-gram·태그·해시태그). 규칙 필터 통과분만."""
    out: set[str] = set()
    title = _QUOTED.sub(" ", video.get("title") or "")
    for seg in _SPLIT.split(title):
        seg = _EMOJI.sub(" ", seg).strip(" ()[]")
        if not seg:
            continue
        words = seg.split()
        grams = [" ".join(words[i:i + n]) for n in (2, 3, 4) for i in range(len(words) - n + 1)]
        cands = [seg] + [g for g in grams if not _DANGLING.search(g)]
        out.update(c for c in cands if _ok_phrase(c, channel_keys))
    for t in video.get("tags") or []:
        if isinstance(t, str) and _ok_phrase(t, channel_keys):
            out.add(t.strip())
    for h in re.findall(r"#([^\s#]{2,30})", f"{video.get('title', '')} {video.get('description', '')}"):
        if _ok_phrase(h, channel_keys):
            out.add(h)
    return out


def _recency(published_at: str, now: datetime) -> float:
    try:
        d = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.5
    age = max(0.0, (now - d).total_seconds() / 86400)
    return max(0.5, 1.0 - 0.5 * min(age, WINDOW_DAYS) / WINDOW_DAYS)


def score(videos: list[dict], now: datetime) -> list[dict]:
    """구절별 점수·채널 수. 채널 3곳 이상만, 점수 내림차순."""
    channel_keys = {_key(v.get("channel") or "") for v in videos if v.get("channel")}
    acc: dict[str, dict] = {}
    seen_vid: set[str] = set()
    for v in videos:
        if v.get("id") in seen_vid:
            continue
        seen_vid.add(v.get("id"))
        w = math.log10(int(v.get("views") or 0) + 10) * _recency(v.get("published_at") or "", now)
        for p in phrases_of(v, channel_keys):
            k = _key(p)
            a = acc.setdefault(k, {"score": 0.0, "channels": set(), "forms": {}})
            a["score"] += w
            a["channels"].add(_key(v.get("channel") or ""))
            a["forms"][p] = a["forms"].get(p, 0) + 1
    out = []
    for k, a in acc.items():
        if len(a["channels"]) < MIN_CHANNELS:
            continue
        form = max(a["forms"].items(), key=lambda kv: (kv[1], " " in kv[0], kv[0] != kv[0].lower(), -len(kv[0])))[0]
        out.append({"kw": form, "score": round(a["score"], 2), "channels": len(a["channels"]),
                    "lang": "ko" if _HANGUL.search(form) else "en"})
    out.sort(key=lambda x: (-x["score"], x["kw"]))
    return _dedupe_contained(out)


def _dedupe_contained(items: list[dict]) -> list[dict]:
    """같은 말이 더 짧은 구절에 통째로 포함되면(점수 차이 20% 이내) 긴 쪽 하나만 남긴다."""
    def close(a: dict, b: dict) -> bool:
        return abs(a["score"] - b["score"]) <= 0.2 * max(a["score"], b["score"])

    kept: list[dict] = []
    for it in items:
        k = _key(it["kw"])
        if any(k in _key(x["kw"]) and close(x, it) for x in kept):
            continue                                    # 이미 더 긴 구절이 있음
        kept = [x for x in kept if not (_key(x["kw"]) in k and close(x, it))]
        kept.append(it)
    kept.sort(key=lambda x: (-x["score"], x["kw"]))
    return kept


def llm_drop_proper_nouns(items: list[dict]) -> list[dict]:
    """상위 LLM_CHECK_TOP 개를 Claude 로 확인 — 가수·곡·채널·브랜드명이면 뺀다. 실패하면 그대로."""
    top = items[:LLM_CHECK_TOP]
    if not top:
        return items
    try:
        from services import music_lyrics
        listing = "\n".join(f"{i}. {it['kw']}" for i, it in enumerate(top))
        raw = music_lyrics._call(
            "너는 유튜브 메타데이터 검수자다. 아래 검색 구절 중 실존 가수·밴드·곡 제목·유튜브 채널·브랜드·"
            "영화/드라마 이름이 들어간 것의 번호만 고른다. 일반 검색어(상황·장르·분위기)는 고르지 않는다.",
            f"{listing}\n\nJSON 하나만 출력: {{\"drop\": [번호, ...]}}",
            max_tokens=300, task="trend_propernoun",
        )
        drop = {int(x) for x in (music_lyrics._extract_json(raw).get("drop") or []) if str(x).isdigit()}
    except Exception as e:  # noqa: BLE001 - LLM 실패 → 규칙·채널 교차 필터만
        logger.warning("[keyword-pool] 고유명사 LLM 확인 실패(규칙 필터만 적용): %s", str(e)[:160])
        return items
    if drop:
        logger.warning("[keyword-pool] 고유명사 제거 %d개: %s", len(drop), ", ".join(top[i]["kw"] for i in sorted(drop) if i < len(top)))
    return [it for i, it in enumerate(top) if i not in drop] + items[LLM_CHECK_TOP:]


def build_pool(videos: list[dict], now: datetime, *, llm: bool = True) -> dict:
    items = score(videos, now)
    if llm:
        items = llm_drop_proper_nouns(items)
    ko = [x for x in items if x["lang"] == "ko"][:POOL_SIZE]
    en = [x for x in items if x["lang"] == "en"][:POOL_SIZE]
    return {"ko": ko, "en": en, "videos": len({v.get("id") for v in videos})}


# ── 저장 (R2) ─────────────────────────────────────────────────────────
def _pool_key(channel: str) -> str:
    return f"{PREFIX}/pool_{channel}.json"


def _recent_key(channel: str) -> str:
    return f"{PREFIX}/recent_titles_{channel}.json"


def _read(key: str) -> dict:
    try:
        from adapters import r2_storage
        obj = r2_storage._get_client().get_object(Bucket=r2_storage._music_bucket(), Key=key)
        data = json.loads(obj["Body"].read().decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 - 없음·읽기 실패 → 빈 풀(기존 제목·해시태그 방식 그대로)
        return {}


def _write(key: str, data: dict) -> bool:
    try:
        from adapters import r2_storage
        r2_storage._get_client().put_object(
            Bucket=r2_storage._music_bucket(), Key=key,
            Body=json.dumps(data, ensure_ascii=False).encode("utf-8"), ContentType="application/json",
        )
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[keyword-pool] 저장 실패 key=%s: %s", key, str(e)[:160])
        return False


def get_pool(channel: str | None) -> dict:
    """채널 키워드 풀(10분 캐시). 없으면 {} — 호출부는 기존 방식으로 동작한다."""
    ch = channel or WHERE
    with _LOCK:
        hit = _cache.get(ch)
        if hit and time.monotonic() - hit[0] < CACHE_SEC:
            return hit[1]
    data = _read(_pool_key(ch))
    with _LOCK:
        _cache[ch] = (time.monotonic(), data)
    return data


# ── 매일 수집 ─────────────────────────────────────────────────────────
def run_daily(now: datetime | None = None, *, client: httpx.Client | None = None) -> dict:
    """채널별 검색 → 풀 갱신 → R2 + music_trends 1행. 키 없으면 건너뜀. 결과 요약 dict."""
    now = (now or datetime.now(timezone.utc)).astimezone(KST)
    key = api_key()
    if not key:
        logger.warning("[keyword-pool] MUSIC_TREND_YOUTUBE_API_KEY 없음 — 키워드 수집 건너뜀"
                       "(업로드 쿼터 보호: YOUTUBE_API_KEY 로 대신 검색하지 않음)")
        return {"skipped": "no_key"}
    summary: dict = {"channels": {}, "searches": 0, "units": 0}
    all_videos: list[dict] = []
    for channel, queries in daily_queries(now).items():
        base: list[dict] = []
        by_genre: dict[str, list[dict]] = {}
        n_search = 0
        for q, genre in queries:
            try:
                vids = search(q, key=key, now=now, client=client)
            except Exception as e:  # noqa: BLE001 - 검색어 1개 실패가 전체를 막지 않게
                logger.warning("[keyword-pool] 검색 실패 channel=%s q=%s: %s", channel, q, str(e)[:160])
                continue
            n_search += 1
            summary["units"] += quota_units(1, len(vids))
            (by_genre.setdefault(genre, []) if genre else base).extend(vids)
        summary["searches"] += n_search
        prev = _read(_pool_key(channel))
        pool = build_pool(base + [v for vs in by_genre.values() for v in vs], now)
        genres = dict(prev.get("genres") or {})
        for g, vids in by_genre.items():
            genres[g] = {**build_pool(vids, now, llm=False), "updated_at": now.isoformat()}
        doc = {"channel": channel, "updated_at": now.isoformat(), "ko": pool["ko"], "en": pool["en"],
               "videos": pool["videos"], "genres": genres,
               "samples": [{"title": v["title"], "views": v["views"], "channel": v["channel"]}
                           for v in sorted(base, key=lambda v: -int(v.get("views") or 0))[:20]]}
        if pool["ko"] or pool["en"]:
            _write(_pool_key(channel), doc)
            with _LOCK:
                _cache.pop(channel, None)
        summary["channels"][channel] = {"ko": len(pool["ko"]), "en": len(pool["en"]), "videos": pool["videos"],
                                        "searches": n_search, "genres_updated": sorted(by_genre)}
        all_videos += base
        logger.warning("[keyword-pool] %s 갱신 — 검색 %d회, 영상 %d개, 키워드 ko %d·en %d, 상위: %s",
                       channel, n_search, pool["videos"], len(pool["ko"]), len(pool["en"]),
                       ", ".join(x["kw"] for x in (pool["ko"][:3] + pool["en"][:2])) or "-")
    logger.warning("[keyword-pool] 오늘 검색 %d회 · 쿼터 약 %d units", summary["searches"], summary["units"])
    _save_trend_row(now, all_videos)
    return summary


def _save_trend_row(now: datetime, videos: list[dict]) -> None:
    """기존 music_trends 형식으로 1행 — 주제 영감·썸네일 톤·대시보드 트렌드 패널이 최신 데이터를 보게."""
    w, h = get_pool(WORKOUT), get_pool(WHERE)
    if not (w.get("ko") or h.get("ko") or w.get("en") or h.get("en")):
        return
    try:
        from services import music_trend
        top = lambda p, lang, n: [x["kw"] for x in (p.get(lang) or [])[:n]]  # noqa: E731
        music_trend.save_insight({
            "mood_keywords": top(h, "ko", 5) + top(h, "en", 3),
            "title_patterns": top(h, "en", 5),
            "hot_situations": top(w, "ko", 5),
            "summary": (f"검색 키워드 상위({now:%m/%d} 수집) — 운동: {', '.join(top(w, 'ko', 3)) or '-'} / "
                        f"where: {', '.join(top(h, 'ko', 3)) or '-'}"),
            "raw_samples": [{"title": v["title"], "view_count": v["views"], "channel": v["channel"]}
                            for v in sorted(videos, key=lambda v: -int(v.get("views") or 0))[:12]],
        })
    except Exception as e:  # noqa: BLE001
        logger.warning("[keyword-pool] music_trends 저장 실패(무시): %s", e)


# ── 메타데이터에 쓰기 ──────────────────────────────────────────────────
def _merged(channel: str | None, genre: str | None) -> tuple[list[dict], list[dict]]:
    pool = get_pool(channel)
    g = (pool.get("genres") or {}).get(genre or "") or {}

    def join(lang: str) -> list[dict]:
        head = list(g.get(lang) or [])[:5]
        seen = {_key(x["kw"]) for x in head}
        return head + [x for x in (pool.get(lang) or []) if _key(x["kw"]) not in seen]
    return join("ko"), join("en")


_INST = re.compile(r"instrumental|no lyrics|가사\s*없|연주|piano|피아노|beats?\b|비트", re.IGNORECASE)


def keywords(channel: str | None, genre: str | None = None, language: str | None = None,
             recent: list[str] | None = None, n: int = 6) -> tuple[list[str], list[str]]:
    """(한국어 검색 키워드, 영어 검색 키워드) 상위 n개. 연주 영상은 연주 계열 우선, 최근 제목에 쓴 건 뒤로."""
    ko, en = _merged(channel, genre)
    used = {_key(x) for x in (recent or [])}

    def order(items: list[dict]) -> list[str]:
        kws = [x["kw"] for x in items]
        if language == "inst":
            kws = [k for k in kws if _INST.search(k)] + [k for k in kws if not _INST.search(k)]
        fresh = [k for k in kws if not any(_key(k) in u for u in used)]
        return (fresh + [k for k in kws if k not in fresh])[:n]
    return order(ko), order(en)


def front_hashtags(channel: str | None, genre: str | None = None, language: str | None = None) -> list[str]:
    """해시태그 앞 3개(제목 위 노출) = 검색량 최상위. 영어 영상은 영어 2·한국어 1, 그 외 한국어 2·영어 1."""
    ko, en = keywords(channel, genre, language, n=3)
    picks = (en[:2] + ko[:1]) if language == "en" else (ko[:2] + en[:1])
    out = []
    for k in picks:
        t = "#" + re.sub(r"[^\w가-힣]", "", k)
        if 2 < len(t) <= 31 and t.lower() not in {x.lower() for x in out}:
            out.append(t)
    return out[:3]


def merge_hashtags(front: list[str], rest: list[str], cap: int = HASHTAG_MAX) -> list[str]:
    """앞 3개 + 기존 조합(중복 제거), 최대 15개."""
    out: list[str] = []
    for t in list(front) + list(rest):
        if t and t.lower() not in {x.lower() for x in out}:
            out.append(t)
    return out[:cap]


def tags_chars(tags: list[str]) -> int:
    """YouTube snippet.tags 길이 계산 — 태그 글자 + 쉼표, 공백 있는 태그는 따옴표 2자."""
    return sum(len(t) + (2 if " " in t else 0) for t in tags) + max(0, len(tags) - 1)


def snippet_tags(channel: str | None, genre: str | None = None, language: str | None = None,
                 extra: list[str] | None = None) -> list[str]:
    """snippet.tags = 키워드 풀(한·영) + extra(장르·상황 단어), 500자 이내. 풀이 없으면 extra 만."""
    ko, en = keywords(channel, genre, language, n=POOL_SIZE)
    order = (en + ko) if language == "en" else (ko + en)
    out: list[str] = []
    for t in order + list(extra or []):
        t = (t or "").strip()
        if not t or t.lower() in {x.lower() for x in out} or len(t) > 60:
            continue
        if tags_chars(out + [t]) > TAGS_MAX_CHARS:
            continue
        out.append(t)
    return out


def recent_titles(channel: str | None) -> list[dict]:
    return list(_read(_recent_key(channel or WHERE)).get("items") or [])


def note_title(channel: str | None, slug: str, ko: str, en: str) -> None:
    """최근 제목 기록(같은 영상 slug 는 1번만) — 다음 제목이 키워드·훅을 겹치지 않게."""
    if not slug:
        return
    ch = channel or WHERE
    items = [x for x in recent_titles(ch) if x.get("slug") != slug]
    items.append({"slug": slug, "ko": ko, "en": en, "at": datetime.now(KST).isoformat()})
    _write(_recent_key(ch), {"items": items[-RECENT_TITLES:]})
