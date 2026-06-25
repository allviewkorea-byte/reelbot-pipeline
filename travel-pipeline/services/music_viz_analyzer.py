"""곡 분석 → 시각 언어(VizSpec) — #20.

장르·무드·상황·제목(+가능하면 가사 톤)으로 색상/부제목/씬키워드/조명을 결정한다.
ANTHROPIC_API_KEY 가 있으면 GPT(저렴 모델)로 풍부화하고, 없거나 실패하면 결정적
fallback(키워드 매핑)으로 **항상 유효한 VizSpec** 을 돌려준다(회귀 안전).

결과는 make_video 가 music_uploads.viz_spec 에 캐싱한다(같은 mix 재렌더 시 재사용).

VizSpec(JSON):
  { primary_color, secondary_color, text_color, subtitle_en,
    dominant_emotion, scene_keywords[], lighting,
    season, location_en, location_category, mood_category }   # #27 (시즌·장소·분위기)
"""

from __future__ import annotations

import logging
import os
import re

from config import CLAUDE_MODEL

logger = logging.getLogger(__name__)

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# #32 금지어 — 시네마틱/네온 등 톤을 흐리는 표현은 프롬프트·결과에서 제거.
_FORBIDDEN_WORDS = ["cinematic", "moody", "dramatic", "neon", "시네마틱", "네온", "드라마틱"]


def _strip_forbidden(text: str) -> str:
    """결과 문자열에서 금지어 제거(대소문자 무시)."""
    out = text
    for w in _FORBIDDEN_WORDS:
        out = re.sub(re.escape(w), "", out, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", out).strip(" ,").strip()

# #27 곡 분석 확장 — 허용 값(검증·#28 자동 플레이리스트 재사용).
_SEASONS = {"spring", "summer", "autumn", "winter", "all_season"}
_LOC_CATS = {"city", "cafe", "nature", "beach", "home", "road"}
_MOOD_CATS = {"chill", "energetic", "sad", "focus", "happy"}

# 장르/무드/상황 키워드 → 색상 프리셋(primary, secondary, text) + 부제·키워드·조명 + 시즌·장소.
_PALETTES: list[dict] = [
    {
        "keys": ["시티팝", "citypop", "city pop", "드라이브", "drive", "driving",
                 "운전", "출근", "퇴근", "commute"],
        "primary": "#7C5CFF", "secondary": "#4ECDFF", "text": "#F5F0E6",
        "subtitle": "morning drive city pop",
        "keywords": ["dawn highway", "city skyline", "open road"],
        "emotion": "free, energetic", "lighting": "warm sunrise",
        "season": "spring", "location_en": "Dawn Highway",
        "location_category": "road", "mood_category": "chill",
    },
    {
        "keys": ["카페", "cafe", "재즈", "jazz", "커피", "coffee", "브런치", "lounge", "라운지"],
        "primary": "#F5A623", "secondary": "#FFD56B", "text": "#F5F0E6",
        "subtitle": "warm afternoon cafe jazz",
        "keywords": ["cozy cafe interior", "coffee cup overhead", "window light"],
        "emotion": "calm, cozy", "lighting": "warm amber light",
        "season": "autumn", "location_en": "Cozy Cafe",
        "location_category": "cafe", "mood_category": "chill",
    },
    {
        "keys": ["이별", "헤어", "breakup", "발라드", "ballad", "슬픔", "sad", "그리움", "눈물"],
        "primary": "#4E6CFF", "secondary": "#9B6CFF", "text": "#E8EAF0",
        "subtitle": "rainy night sad ballad",
        "keywords": ["rain-streaked window", "empty night street", "soft city lights"],
        "emotion": "melancholic, tender", "lighting": "cool moonlight",
        "season": "winter", "location_en": "Rainy Street",
        "location_category": "city", "mood_category": "sad",
    },
    {
        "keys": ["운동", "헬스", "workout", "gym", "러닝", "running", "동기", "motivat",
                 "fitness", "트레이닝"],
        "primary": "#FF4E4E", "secondary": "#FF9B3D", "text": "#FFFFFF",
        "subtitle": "high energy workout beats",
        "keywords": ["coastal running trail", "city sunrise", "ocean horizon"],
        "emotion": "powerful, driven", "lighting": "bright daylight",
        "season": "summer", "location_en": "Coastal Run",
        "location_category": "beach", "mood_category": "energetic",
    },
    {
        "keys": ["수면", "잠", "취침", "sleep", "공부", "스터디", "study", "집중", "focus",
                 "독서", "lofi", "lo-fi"],
        "primary": "#34D399", "secondary": "#A7F3D0", "text": "#F0F5EE",
        "subtitle": "calm late night lofi",
        "keywords": ["quiet desk by window", "moonlit room", "still lake"],
        "emotion": "soothing, focused", "lighting": "soft dim light",
        "season": "all_season", "location_en": "Quiet Room",
        "location_category": "home", "mood_category": "focus",
    },
]
_DEFAULT_PALETTE = {
    "primary": "#7C5CFF", "secondary": "#4ECDFF", "text": "#F5F0E6",
    "subtitle": "smooth music vibes",
    "keywords": ["city skyline", "soft bokeh lights", "calm horizon"],
    "emotion": "smooth, warm", "lighting": "warm light",
    "season": "all_season", "location_en": "City View",
    "location_category": "city", "mood_category": "chill",
}


def _haystack(theme: dict) -> str:
    return " ".join(
        str(theme.get(k, "")) for k in ("genre", "mood", "situation", "title_kr", "slug")
    ).lower()


def _match_palette(theme: dict) -> dict:
    hay = _haystack(theme)
    for p in _PALETTES:
        if any(k.lower() in hay for k in p["keys"]):
            return p
    return _DEFAULT_PALETTE


def _fallback_spec(theme: dict) -> dict:
    """GPT 없이도 항상 유효한 VizSpec(결정적 키워드 매핑)."""
    p = _match_palette(theme)
    return {
        "primary_color": p["primary"],
        "secondary_color": p["secondary"],
        "text_color": p["text"],
        "subtitle_en": p["subtitle"],
        "dominant_emotion": p["emotion"],
        "scene_keywords": list(p["keywords"]),
        "lighting": p["lighting"],
        "season": p["season"],
        "location_en": p["location_en"],
        "location_category": p["location_category"],
        "mood_category": p["mood_category"],
    }


def _coerce(spec: dict, fallback: dict) -> dict:
    """GPT 출력 검증/정규화 — 잘못된 필드는 fallback 으로 대체(항상 유효 보장)."""
    out = dict(fallback)
    if not isinstance(spec, dict):
        return out
    for k in ("primary_color", "secondary_color", "text_color"):
        v = str(spec.get(k, "")).strip()
        if _HEX.match(v):
            out[k] = v.upper()
    sub = str(spec.get("subtitle_en", "")).strip().lower()
    if 2 <= len(sub) <= 80:
        out["subtitle_en"] = sub
    emo = str(spec.get("dominant_emotion", "")).strip()
    if emo:
        out["dominant_emotion"] = emo[:60]
    light = _strip_forbidden(str(spec.get("lighting", "")).strip())
    if light:
        out["lighting"] = light[:60]
    kws = spec.get("scene_keywords")
    if isinstance(kws, list):
        clean = [_strip_forbidden(str(x).strip()) for x in kws if str(x).strip()]
        clean = [c for c in clean if c][:5]
        if clean:
            out["scene_keywords"] = clean
    # #27 시즌·장소·분위기 — 허용 값만 채택, 아니면 fallback 유지.
    season = str(spec.get("season", "")).strip().lower()
    if season in _SEASONS:
        out["season"] = season
    loc = str(spec.get("location_en", "")).strip()
    if 2 <= len(loc) <= 40:
        out["location_en"] = loc
    lcat = str(spec.get("location_category", "")).strip().lower()
    if lcat in _LOC_CATS:
        out["location_category"] = lcat
    mcat = str(spec.get("mood_category", "")).strip().lower()
    if mcat in _MOOD_CATS:
        out["mood_category"] = mcat
    return out


def _gpt_spec(theme: dict, fallback: dict, *, model: str | None = None) -> dict:
    from services import music_lyrics

    mdl = (model or os.getenv("MUSIC_VIZ_MODEL") or CLAUDE_MODEL).strip()
    system = (
        "You are an art director for a music video channel with a landscape/city/nature "
        "visual identity (no people focus). Given a song's metadata, decide its visual "
        "language. Return STRICT JSON only with keys: "
        "primary_color, secondary_color, text_color (all #RRGGBB hex), "
        "subtitle_en (one poetic lowercase english line, 5-8 words), "
        "dominant_emotion (2-3 words), scene_keywords (3-5 short english LANDSCAPE/place "
        "phrases, no people), lighting (short english), "
        "season (one of: spring, summer, autumn, winter, all_season), "
        "location_en (a short evocative english PLACE name for a WHERE label, e.g. "
        "'Blue Pool', 'New York', 'Cozy Cafe', 'Rainy Street'), "
        "location_category (one of: city, cafe, nature, beach, home, road), "
        "mood_category (one of: chill, energetic, sad, focus, happy). "
        "Colors must match genre/mood. Bright/clear daylight tone preferred. "
        "Never use these words: cinematic, moody, dramatic, neon. No markdown, no commentary."
    )
    user = (
        f"genre: {theme.get('genre','')}\n"
        f"mood: {theme.get('mood','')}\n"
        f"situation/concept: {theme.get('situation','')}\n"
        f"title: {theme.get('title_kr','')}\n"
        f"lyric tone: {theme.get('lyric_tone') or ''}\n"
        f"Suggested palette (use as a hint): primary {fallback['primary_color']}, "
        f"secondary {fallback['secondary_color']}."
    )
    raw = music_lyrics._call(system, user, max_tokens=400, model=mdl)
    data = music_lyrics._extract_json(raw)
    return _coerce(data if isinstance(data, dict) else {}, fallback)


def analyze_song(theme: dict, mix: dict | None = None, *, use_gpt: bool = True) -> dict:
    """곡 → VizSpec. GPT 가능하면 풍부화, 아니면 fallback. 항상 유효한 dict."""
    fallback = _fallback_spec(theme)
    if not use_gpt:
        return fallback
    try:
        from services import music_lyrics
        if not music_lyrics.is_available():
            return fallback
        return _gpt_spec(theme, fallback)
    except Exception as e:  # noqa: BLE001 - GPT 실패 시 결정적 fallback(회귀 안전)
        logger.warning("[music-viz] 곡 분석 GPT 실패 → fallback: %s", e)
        return fallback
