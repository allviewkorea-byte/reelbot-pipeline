"""음악 트렌드 분석 (Rooftop Music) — 인기 플레이리스트 영상 → 성공 패턴 인사이트.

유튜브 인기 음악 영상을 검색(YouTubeDataAdapter 재사용)해 제목·조회수·채널을 모으고,
GPT(저렴 모델)로 "요즘 먹히는 무드·제목 경향·인기 상황"을 추출한다. 결과는 Supabase
music_trends 에 저장하고, 최신 1건을 주제 생성의 **영감(가중치 아님)** 으로 쓴다.

⚠️ quota: 검색 1회 = 101 units(search 100 + videos.list 1). 키워드 수를 제한한다
(기본 7개 ≈ 707 units, 일일 10,000 한도 내 여유). YOUTUBE_API_KEY 는 백곰과 공유.
신규 의존성 없음(GPT 는 music_lyrics._call/_extract_json, 저장은 music_store PostgREST).
"""

from __future__ import annotations

import logging
import os

import httpx

from services import music_lyrics
from services.music_store import _http_err, _supabase_cfg

logger = logging.getLogger(__name__)

_TABLE = "music_trends"
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# 글로벌 음악 플레이리스트 키워드(영어 — 헌법 장르·상황 기반). quota 위해 7개로 제한.
DEFAULT_KEYWORDS = [
    "study music playlist",
    "workout music playlist",
    "lofi hip hop",
    "sleep music",
    "rainy day jazz playlist",
    "city pop playlist",
    "focus music",
]


def _model(model: str | None = None) -> str:
    return (model or os.getenv("MUSIC_THEME_MODEL") or _DEFAULT_MODEL).strip()


def is_available() -> bool:
    """유튜브 검색 + GPT 둘 다 가능해야 분석 실행 가능."""
    return bool(os.getenv("YOUTUBE_API_KEY")) and music_lyrics.is_available()


# ── 수집 ─────────────────────────────────────────────────────────────────
def collect_samples(keywords: list[str] | None = None, *, per_keyword: int = 8) -> list[dict]:
    """키워드별 인기 영상(롱폼) 상위 per_keyword 개 메타 수집(YouTubeDataAdapter 재사용)."""
    from adapters.data.youtube_data_adapter import YouTubeDataAdapter

    adapter = YouTubeDataAdapter()
    if not adapter.is_available():
        raise RuntimeError("YOUTUBE_API_KEY 미설정 — 트렌드 수집 불가")

    kws = keywords or DEFAULT_KEYWORDS
    samples: list[dict] = []
    for kw in kws:
        try:
            vids = adapter.search_top_videos(kw, format="long", max_results=20)
        except Exception as e:  # noqa: BLE001 - 키워드 1개 실패가 전체를 막지 않게
            logger.warning("[music-trend] 검색 실패(kw=%s): %s", kw, e)
            continue
        for v in vids[:per_keyword]:
            samples.append({
                "keyword": kw,
                "title": v.get("title", ""),
                "view_count": int(v.get("view_count", 0) or 0),
                "channel": v.get("channel_title", ""),
                "tags": (v.get("tags") or [])[:8],
            })
    logger.info("[music-trend] 수집 %d개 샘플(키워드 %d개)", len(samples), len(kws))
    return samples


# ── 분석(GPT) ────────────────────────────────────────────────────────────
def analyze(samples: list[dict], *, model: str | None = None) -> dict:
    """수집 샘플 → 성공 패턴 인사이트 JSON(mood/title/situation/summary + raw_samples)."""
    if not samples:
        raise ValueError("분석할 샘플이 없습니다.")

    lines = [
        f"[{s['keyword']}] {s['title']} | {s['view_count']:,}회 | {s['channel']}"
        for s in samples
    ]
    sample_text = "\n".join(lines[:80])
    system = (
        "너는 유튜브 음악 트렌드 분석가다. 인기 음악 플레이리스트 영상 데이터에서 "
        "성공 패턴(무드·제목 경향·인기 상황)을 뽑아낸다. JSON 외 텍스트 금지."
    )
    user = (
        f"=== 인기 음악 영상 샘플(제목 | 조회수 | 채널) ===\n{sample_text}\n\n"
        "위 데이터에서 성공 패턴을 분석해 JSON으로만 출력:\n"
        "{\"mood_keywords\":[자주 등장하는 무드 5~8개],"
        "\"title_patterns\":[제목 경향 3~5개(이모지·관용구·상황강조 등)],"
        "\"hot_situations\":[인기 상황/시간대 3~5개],"
        "\"summary\":\"한 줄 인사이트(한국어)\"}\n"
        "JSON 외 다른 텍스트 금지."
    )
    data = music_lyrics._extract_json(
        music_lyrics._call(system, user, max_tokens=900, model=_model(model))
    )
    top = sorted(samples, key=lambda s: s.get("view_count", 0), reverse=True)[:12]
    return {
        "mood_keywords": data.get("mood_keywords") or [],
        "title_patterns": data.get("title_patterns") or [],
        "hot_situations": data.get("hot_situations") or [],
        "summary": data.get("summary") or "",
        "raw_samples": [
            {"title": s["title"], "view_count": s["view_count"], "channel": s["channel"]}
            for s in top
        ],
    }


def run_analysis(keywords: list[str] | None = None, *, persist: bool = True) -> dict:
    """수집 → 분석 → (옵션)저장. cron/검증 진입점. Returns 인사이트 dict."""
    samples = collect_samples(keywords)
    insight = analyze(samples)
    if persist:
        save_insight(insight)
    return insight


# ── 저장/조회 (music_store PostgREST 패턴 재사용) ─────────────────────────
def save_insight(insight: dict) -> dict:
    """인사이트 1건 insert. {stored, error}. 미설정/실패해도 분석 자체는 성공."""
    url, key = _supabase_cfg()
    if not (url and key):
        logger.warning("[music-trend] SUPABASE 미설정 — 인사이트 저장 생략")
        return {"stored": False, "error": "supabase 미설정"}
    record = {
        "mood_keywords": insight.get("mood_keywords") or [],
        "title_patterns": insight.get("title_patterns") or [],
        "hot_situations": insight.get("hot_situations") or [],
        "summary": insight.get("summary") or "",
        "raw_samples": insight.get("raw_samples") or [],
    }
    try:
        headers = {
            "apikey": key, "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=30.0) as c:
            r = c.post(f"{url}/rest/v1/{_TABLE}", headers=headers, json=[record])
            r.raise_for_status()
        logger.info("[music-trend] 인사이트 저장 OK")
        return {"stored": True, "error": None}
    except Exception as e:  # noqa: BLE001
        msg = _http_err(e)
        logger.warning("[music-trend] 인사이트 저장 실패: %s", msg)
        return {"stored": False, "error": msg}


def get_latest() -> dict | None:
    """최신 인사이트 1건(analyzed_at 역순). 미설정/없음/오류 시 None."""
    url, key = _supabase_cfg()
    if not (url and key):
        return None
    try:
        headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        params = {
            "select": "analyzed_at,mood_keywords,title_patterns,hot_situations,summary,raw_samples",
            "order": "analyzed_at.desc",
            "limit": "1",
        }
        with httpx.Client(timeout=30.0) as c:
            r = c.get(f"{url}/rest/v1/{_TABLE}", headers=headers, params=params)
            r.raise_for_status()
            rows = r.json()
        return rows[0] if rows else None
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-trend] 최신 인사이트 조회 실패: %s", _http_err(e))
        return None
