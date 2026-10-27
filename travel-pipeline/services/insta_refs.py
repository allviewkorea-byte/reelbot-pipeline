"""인스타 쇼핑 A2-1 — 유튜브 레퍼런스 수집 + 룩 분석.

- 수집(YouTube Data API 공식, 크롤링·영상 다운로드·프레임 추출 없음): 검색어 풀에서 AI 가 오늘 검색어를 고르고
  → search.list(최근 30일·조회수 순, 100유닛) → videos.list(통계·설명란, 1유닛) → 썸네일(최고 해상도)만
  R2 insta/refs/{id}.jpg 에 화면 표시용 사본. 같은 영상은 다시 넣지 않는다(ig_refs.video_id PK).
- 쿼터: 유튜브 하루 유닛 상한 YT_DAILY_UNIT_CAP — ig_api_usage 에 KST 날짜별로 기록·대시보드 표시.
  키는 검색 전용 키만(INSTA_YOUTUBE_API_KEY → MUSIC_TREND_YOUTUBE_API_KEY). 업로드 쿼터(YOUTUBE_API_KEY)는
  쓰지 않는다(music_keyword_pool 과 같은 원칙 — 업로드가 쿼터 부족으로 실패하면 안 됨).
- 분석(Claude 비전): 썸네일 + 제목·설명란 → 룩 명세서 JSON(룩별 아이템: 종류·색 이름+HEX·핏·기장·소재·디테일·
  한국 쇼핑몰식 검색어 2~3개, 분위기·상황·계절). 설명란 착용 제품(상품명·브랜드)은 가장 강한 단서로 따로.
  레퍼런스 이미지·문구는 조합·분위기 참고용 — 결과물·캡션에 그대로 쓰지 않는다. 얼굴·텍스트는 분석만.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import httpx

from adapters import r2_storage
from services import character_studio_gen as gen
from services import insta_outfit as io
from services import insta_outfit_plan as P
from services.music_store import _http_err, _supabase_cfg

logger = logging.getLogger(__name__)

API = "https://www.googleapis.com/youtube/v3"
YT_DAILY_UNIT_CAP = 1500         # 하루 상한(유닛) — search 100 × 14 + videos.list (대표 승인 2026-10-27, 음악 ~1,800 합쳐도 10,000 내)
SEARCH_COST, VIDEOS_COST = 100, 1
SEARCHES_PER_RUN = 3             # 1회 수집에서 쓰는 검색어 수
PER_QUERY = 4                    # 검색어당 저장할 영상(조회수 상위)
MAX_AGE_DAYS = 30
ANALYZE_PER_RUN = 12

QUERY_POOL = [
    "가을 코디", "겨울 코디", "봄 코디", "여름 코디", "출근룩", "데일리룩 여자", "하객룩", "데이트룩",
    "오피스룩 여자", "주말 코디 여자", "니트 코디", "코트 코디", "트렌치코트 코디", "가디건 코디", "청바지 코디 여자",
    "슬랙스 코디 여자", "원피스 코디", "미니멀룩", "꾸안꾸 코디", "키 큰 여자 코디", "여행 코디", "캠퍼스룩",
]


class RefsError(RuntimeError):
    """수집·분석 실패(502)."""


# ── Supabase(PostgREST) — 테이블 지정형 ─────────────────────────────────
def rest(table: str, method: str, *, params: dict | None = None, json_body: object = None,
         prefer: str | None = None) -> list[dict]:
    url, key = _supabase_cfg()
    if not (url and key):
        raise RefsError("Supabase 미설정")
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.request(method, f"{url}/rest/v1/{table}", headers=headers, params=params, json=json_body)
            r.raise_for_status()
            data = r.json() if r.content else []
    except Exception as e:  # noqa: BLE001
        raise RefsError(f"저장소 오류({table}): {_http_err(e)}") from e
    return data if isinstance(data, list) else []


def _kst_today(now: datetime | None = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(P.KST).date()


# ── 사용량 ──────────────────────────────────────────────────────────────
def usage(api: str, now: datetime | None = None) -> dict:
    day = _kst_today(now).isoformat()
    rows = rest("ig_api_usage", "GET", params={"select": "*", "day": f"eq.{day}", "api": f"eq.{api}"})
    row = rows[0] if rows else {"day": day, "api": api, "units": 0, "calls": 0}
    return {**row, "cap": YT_DAILY_UNIT_CAP if api == "youtube" else None}


def add_usage(api: str, units: int, now: datetime | None = None) -> None:
    cur = usage(api, now)
    rest("ig_api_usage", "POST", params={"on_conflict": "day,api"},
         json_body=[{"day": cur["day"], "api": api, "units": int(cur["units"]) + units, "calls": int(cur["calls"]) + 1}],
         prefer="resolution=merge-duplicates,return=minimal")


# ── 검색어 고르기 ────────────────────────────────────────────────────────
_EVENTS = {(12, 24): "크리스마스 데이트룩", (12, 31): "연말 파티룩", (2, 14): "발렌타인 데이트룩",
           (5, 1): "결혼식 하객룩", (10, 1): "가을 결혼식 하객룩"}


def fallback_queries(now: datetime, n: int) -> list[str]:
    """AI 없이: 계절 코디 + 요일 생활(출근/데이트/주말) + 다가오는 이벤트."""
    d = now.astimezone(P.KST).date()
    season = {"spring": "봄 코디", "summer": "여름 코디", "autumn": "가을 코디", "winter": "겨울 코디"}[P.season_of(d)]
    life = "출근룩" if d.weekday() <= 3 else ("데이트룩" if d.weekday() == 4 else "주말 코디 여자")
    out = [season, life, "데일리룩 여자"]
    for (m, day), q in _EVENTS.items():
        try:
            ev = date(d.year, m, day)
        except ValueError:
            continue
        if 0 <= (ev - d).days <= 21:
            out.insert(1, q)
    return list(dict.fromkeys(out))[:n]


_Q_SYSTEM = (
    "You pick YouTube search queries (Korean) to find recent women's outfit/lookbook videos for a Korean fashion "
    "Instagram account. Consider the date's season, weekday and upcoming events. Return ONE JSON object: "
    '{"queries": ["...", ...]} — prefer the given pool, you may add at most one new query. Each 2~20 chars.'
)


def choose_queries(now: datetime, n: int = SEARCHES_PER_RUN, llm: Callable | None = None, recent: list[str] | None = None) -> list[str]:
    from services import music_lyrics
    llm = llm or (lambda s, u: music_lyrics._call(s, u, max_tokens=200, task="insta_refs_query"))
    d = now.astimezone(P.KST).date()
    try:
        data = music_lyrics._extract_json(llm(_Q_SYSTEM, json.dumps({
            "date": d.isoformat(), "weekday": P.WEEKDAYS[d.weekday()]["ko"], "season": P.season_of(d),
            "pool": QUERY_POOL, "recently_used": recent or [], "count": n}, ensure_ascii=False)))
        qs = [q.strip() for q in (data.get("queries") or []) if isinstance(q, str) and 2 <= len(q.strip()) <= 20]
        qs = list(dict.fromkeys(qs))[:n]
        if qs:
            return qs
    except Exception as e:  # noqa: BLE001
        logger.warning("[insta-refs] 검색어 AI 실패 → 기본 규칙: %s", str(e)[:160])
    return fallback_queries(now, n)


# ── 유튜브 ───────────────────────────────────────────────────────────────
def yt_key() -> str:
    return (os.getenv("INSTA_YOUTUBE_API_KEY") or os.getenv("MUSIC_TREND_YOUTUBE_API_KEY") or "").strip()


def _http_get(url: str, params: dict) -> dict:
    with httpx.Client(timeout=30.0) as c:
        r = c.get(url, params=params)
        r.raise_for_status()
        return r.json()


def _best_thumb(thumbs: dict) -> str | None:
    for k in ("maxres", "standard", "high", "medium", "default"):
        if (thumbs or {}).get(k, {}).get("url"):
            return thumbs[k]["url"]
    return None


_PRODUCT_LINE = re.compile(r"(상의|하의|아우터|니트|코트|자켓|재킷|셔츠|블라우스|팬츠|바지|스커트|치마|원피스|가디건|신발|"
                           r"구두|부츠|스니커즈|가방|백|top|bottom|outer|shoes|bag|coat|jacket|knit|skirt|pants|dress)", re.I)


def product_lines(description: str) -> list[str]:
    """설명란에서 착용 제품처럼 보이는 줄(분석에 가장 강한 단서로 넘김)."""
    lines = [ln.strip(" -•·*\t") for ln in (description or "").splitlines()]
    return [ln[:120] for ln in lines if ln and _PRODUCT_LINE.search(ln) and len(ln) <= 160][:25]


def existing_ids(ids: list[str]) -> set[str]:
    if not ids:
        return set()
    rows = rest("ig_refs", "GET", params={"select": "video_id", "video_id": f"in.({','.join(ids)})"})
    return {r["video_id"] for r in rows}


def _save_thumb(video_id: str, url: str, download: Callable[[str, Path], Path]) -> str | None:
    if not r2_storage.is_available():
        return None
    with tempfile.TemporaryDirectory() as d:
        p = download(url, Path(d) / "t.jpg")
        key = f"insta/refs/{video_id}.jpg"
        r2_storage.upload_image(str(p), key, bucket=r2_storage._character_bucket(),
                                public_base_url=r2_storage._character_public_base(), content_type="image/jpeg")
        return key


def collect(now: datetime | None = None, *, http_get: Callable | None = None, llm: Callable | None = None,
            download: Callable | None = None) -> dict:
    """오늘 검색어로 레퍼런스 수집. 유닛 상한을 넘기 전에 멈춘다. → 요약 dict."""
    now = now or datetime.now(timezone.utc)
    http_get = http_get or _http_get
    download = download or io._download
    key = yt_key()
    if not key:
        return {"skipped": "유튜브 검색 키 없음(INSTA_YOUTUBE_API_KEY)", "saved": 0}
    used = int(usage("youtube", now)["units"])
    recent = [r.get("query") for r in rest("ig_refs", "GET", params={"select": "query", "order": "collected_at.desc", "limit": "30"})]
    queries = choose_queries(now, SEARCHES_PER_RUN, llm, [q for q in recent if q])
    after = (now - timedelta(days=MAX_AGE_DAYS)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = {"queries": [], "saved": 0, "dupes": 0, "units": 0, "stopped_by_quota": False}
    for q in queries:
        if used + SEARCH_COST + VIDEOS_COST > YT_DAILY_UNIT_CAP:
            out["stopped_by_quota"] = True
            break
        s = http_get(f"{API}/search", {"key": key, "part": "snippet", "q": q, "type": "video", "order": "viewCount",
                                       "publishedAfter": after, "regionCode": "KR", "relevanceLanguage": "ko",
                                       "maxResults": 15, "safeSearch": "strict"})
        used += SEARCH_COST
        out["units"] += SEARCH_COST
        add_usage("youtube", SEARCH_COST, now)
        ids = [it["id"]["videoId"] for it in s.get("items", []) if it.get("id", {}).get("videoId")]
        have = existing_ids(ids)
        fresh = [i for i in ids if i not in have]
        out["dupes"] += len(ids) - len(fresh)
        out["queries"].append({"query": q, "found": len(ids), "new": len(fresh)})
        if not fresh:
            continue
        v = http_get(f"{API}/videos", {"key": key, "part": "snippet,statistics", "id": ",".join(fresh[:50])})
        used += VIDEOS_COST
        out["units"] += VIDEOS_COST
        add_usage("youtube", VIDEOS_COST, now)
        vids = sorted(v.get("items", []), key=lambda x: int((x.get("statistics") or {}).get("viewCount") or 0), reverse=True)
        for it in vids[:PER_QUERY]:
            sn = it.get("snippet") or {}
            vid = it["id"]
            thumb = _best_thumb(sn.get("thumbnails") or {})
            try:
                thumb_key = _save_thumb(vid, thumb, download) if thumb else None
            except Exception as e:  # noqa: BLE001 - 썸네일 실패해도 기록은 남긴다(분석은 건너뜀)
                logger.warning("[insta-refs] 썸네일 저장 실패 %s: %s", vid, str(e)[:120])
                thumb_key = None
            rest("ig_refs", "POST", params={"on_conflict": "video_id"}, prefer="resolution=ignore-duplicates,return=minimal",
                 json_body=[{"video_id": vid, "query": q, "title": (sn.get("title") or "")[:300],
                             "channel_title": (sn.get("channelTitle") or "")[:120],
                             "description": (sn.get("description") or "")[:3000],
                             "views": int((it.get("statistics") or {}).get("viewCount") or 0),
                             "published_at": sn.get("publishedAt"), "thumb_key": thumb_key}])
            out["saved"] += 1
    return out


# ── 분석 ─────────────────────────────────────────────────────────────────
_ANALYZE_SYSTEM = (
    "You analyze ONE YouTube outfit video thumbnail plus its title and description for a Korean women's fashion "
    "account. Write a look spec. If the thumbnail shows several distinct outfits, split them into separate looks "
    "(max 3). Do NOT describe faces or identities; ignore overlaid text except clothing info.\n"
    "Return ONE JSON object only:\n"
    '{"looks": [{"concept": "<짧은 한글 컨셉 이름, 12자 이내>", "mood": "<짧은 한글>", '
    '"situations": ["출근"|"데이트"|"주말"|"하객"|"여행"|...], "seasons": ["spring"|"summer"|"autumn"|"winter"], '
    '"items": [{"kind": "top|bottoms|dress|outerwear|shoes|bag|accessory", "color_name": "<한글 색 이름>", '
    '"hex": "#RRGGBB", "fit": "slim|regular|over", "length": "<e.g. cropped, hip, mid-thigh, knee, midi, ankle, full>", '
    '"material": "<한글>", "details": "<buttons count, collar, pockets, pattern — short English>", '
    '"queries": ["<한국 쇼핑몰식 검색어>", "...", "..."]}]}], '
    '"desc_products": [{"name": "<상품명>", "brand": "<브랜드 or 빈 값>", "kind": "<kind or 빈 값>"}]}\n'
    "Queries: 2~3 per item, how a Korean shopper would search (e.g. '여성 베이지 울 롱코트', '와이드 슬랙스 여자 차콜'). "
    "Use the description's product list as the strongest clue for item names."
)

_FITS = {"slim", "regular", "over"}
_SEASONS = {"spring", "summer", "autumn", "winter"}
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def normalize_analysis(data: dict) -> dict:
    looks = []
    for lk in (data.get("looks") or [])[:3]:
        if not isinstance(lk, dict):
            continue
        items = []
        for it in (lk.get("items") or [])[:6]:
            if not isinstance(it, dict) or it.get("kind") not in P.PRODUCT_KINDS:
                continue
            qs = [q.strip() for q in (it.get("queries") or []) if isinstance(q, str) and 2 <= len(q.strip()) <= 40]
            if not qs:
                continue
            items.append({
                "kind": it["kind"], "color_name": str(it.get("color_name") or "")[:20],
                "hex": it.get("hex") if isinstance(it.get("hex"), str) and _HEX.match(it["hex"]) else None,
                "fit": it.get("fit") if it.get("fit") in _FITS else "regular",
                "length": str(it.get("length") or "")[:30], "material": str(it.get("material") or "")[:20],
                "details": str(it.get("details") or "")[:160], "queries": list(dict.fromkeys(qs))[:3],
            })
        if not items:
            continue
        looks.append({
            "concept": str(lk.get("concept") or "데일리룩")[:12], "mood": str(lk.get("mood") or "")[:20],
            "situations": [str(s)[:10] for s in (lk.get("situations") or [])][:4],
            "seasons": [s for s in (lk.get("seasons") or []) if s in _SEASONS],
            "items": items,
        })
    prods = [{"name": str(p.get("name") or "")[:80], "brand": str(p.get("brand") or "")[:40], "kind": p.get("kind") or ""}
             for p in (data.get("desc_products") or []) if isinstance(p, dict) and p.get("name")][:20]
    return {"looks": looks, "desc_products": prods}


def analyze(row: dict, *, vision: Callable | None = None, download: Callable | None = None) -> dict:
    """레퍼런스 1개 → 룩 명세서 저장. 룩이 하나도 없으면 failed."""
    vision = vision or io._vision_json
    download = download or io._download
    vid = row["video_id"]
    try:
        if not row.get("thumb_key"):
            raise RefsError("썸네일 없음")
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            src = download(io.public_url(row["thumb_key"]), tmp / "t.jpg")
            small = gen._small_jpeg(src, tmp / "s.jpg")
            ask = json.dumps({"title": row.get("title"), "description": (row.get("description") or "")[:1500],
                              "product_lines": product_lines(row.get("description") or "")}, ensure_ascii=False)
            spec = normalize_analysis(vision(_ANALYZE_SYSTEM, [small], ask, "insta_refs_analyze", 1500))
        if not spec["looks"]:
            raise RefsError("분석된 룩이 없음")
        rest("ig_refs", "PATCH", params={"video_id": f"eq.{vid}"}, prefer="return=minimal",
             json_body={"analysis": spec, "desc_products": spec["desc_products"], "status": "analyzed", "error": None})
        return spec
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:300]
        logger.warning("[insta-refs] 분석 실패 %s: %s", vid, msg)
        rest("ig_refs", "PATCH", params={"video_id": f"eq.{vid}"}, prefer="return=minimal",
             json_body={"status": "failed", "error": msg})
        return {"error": msg}


# ── 실행(하루 1회 + 수동) ────────────────────────────────────────────────
_STATE = {"running": False, "last": None, "started_at": None}
_LOCK = threading.Lock()


def status() -> dict:
    with _LOCK:
        return dict(_STATE)


def try_begin() -> bool:
    with _LOCK:
        if _STATE["running"]:
            return False
        _STATE.update(running=True, started_at=datetime.now(timezone.utc).isoformat())
        return True


def run(*, force: bool = False, **deps) -> dict:
    """수집(오늘 이미 했으면 건너뜀, force 면 다시) → 새 레퍼런스 분석. try_begin() 후 호출."""
    try:
        now = deps.pop("now", None) or datetime.now(timezone.utc)
        summary: dict = {}
        today_calls = int(usage("youtube", now)["calls"])
        if today_calls and not force:
            summary["collect"] = {"skipped": "오늘은 이미 모았어요", "saved": 0}
        else:
            summary["collect"] = collect(now, **{k: v for k, v in deps.items() if k in ("http_get", "llm", "download")})
        rows = rest("ig_refs", "GET", params={"select": "*", "status": "eq.new", "order": "views.desc",
                                              "limit": str(ANALYZE_PER_RUN)})
        done = 0
        for r in rows:
            spec = analyze(r, **{k: v for k, v in deps.items() if k in ("vision", "download")})
            done += 0 if spec.get("error") else 1
        summary["analyzed"] = done
        summary["usage"] = usage("youtube", now)
        with _LOCK:
            _STATE["last"] = {**summary, "finished_at": datetime.now(timezone.utc).isoformat()}
        return summary
    except Exception as e:  # noqa: BLE001
        with _LOCK:
            _STATE["last"] = {"error": str(e)[:300], "finished_at": datetime.now(timezone.utc).isoformat()}
        raise
    finally:
        with _LOCK:
            _STATE["running"] = False


def list_refs(limit: int = 20) -> list[dict]:
    rows = rest("ig_refs", "GET", params={"select": "video_id,query,title,channel_title,views,published_at,thumb_key,"
                                                    "analysis,status,error,collected_at",
                                          "order": "collected_at.desc", "limit": str(max(1, min(int(limit), 50)))})
    return [{**r, "thumb_url": io.public_url(r.get("thumb_key")), "video_url": f"https://www.youtube.com/watch?v={r['video_id']}"}
            for r in rows]
