"""곡 분석 → 시각 언어(VizSpec) — #20.

장르·무드·상황·제목(+가능하면 가사 톤)으로 색상/부제목/씬키워드/조명을 결정한다.
ANTHROPIC_API_KEY 가 있으면 GPT(저렴 모델)로 풍부화하고, 없거나 실패하면 결정적
fallback(키워드 매핑)으로 **항상 유효한 VizSpec** 을 돌려준다(회귀 안전).

결과는 make_video 가 music_uploads.viz_spec 에 캐싱한다(같은 mix 재렌더 시 재사용).

VizSpec(JSON):
  { primary_color, secondary_color, text_color, subtitle_en,
    dominant_emotion, scene_keywords[], lighting }
"""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# 장르/무드/상황 키워드 → 색상 프리셋(primary, secondary, text) + 부제·키워드·조명.
_PALETTES: list[dict] = [
    {
        "keys": ["시티팝", "citypop", "city pop", "드라이브", "drive", "driving",
                 "운전", "출근", "퇴근", "commute"],
        "primary": "#7C5CFF", "secondary": "#4ECDFF", "text": "#F5F0E6",
        "subtitle": "morning drive city pop",
        "keywords": ["dawn road", "open car window", "wind"],
        "emotion": "free, energetic", "lighting": "warm sunrise",
    },
    {
        "keys": ["카페", "cafe", "재즈", "jazz", "커피", "coffee", "브런치", "lounge", "라운지"],
        "primary": "#F5A623", "secondary": "#FFD56B", "text": "#F5F0E6",
        "subtitle": "warm afternoon cafe jazz",
        "keywords": ["cozy cafe", "coffee cup", "window light"],
        "emotion": "calm, cozy", "lighting": "warm amber light",
    },
    {
        "keys": ["이별", "헤어", "breakup", "발라드", "ballad", "슬픔", "sad", "그리움", "눈물"],
        "primary": "#4E6CFF", "secondary": "#9B6CFF", "text": "#E8EAF0",
        "subtitle": "rainy night sad ballad",
        "keywords": ["rainy window", "night city", "neon glow"],
        "emotion": "melancholic, tender", "lighting": "cool moonlight",
    },
    {
        "keys": ["운동", "헬스", "workout", "gym", "러닝", "running", "동기", "motivat",
                 "fitness", "트레이닝"],
        "primary": "#FF4E4E", "secondary": "#FF9B3D", "text": "#FFFFFF",
        "subtitle": "high energy workout beats",
        "keywords": ["running track", "city sunrise", "motion blur"],
        "emotion": "powerful, driven", "lighting": "bright daylight",
    },
    {
        "keys": ["수면", "잠", "취침", "sleep", "공부", "스터디", "study", "집중", "focus",
                 "독서", "lofi", "lo-fi"],
        "primary": "#34D399", "secondary": "#A7F3D0", "text": "#F0F5EE",
        "subtitle": "calm late night lofi",
        "keywords": ["quiet desk", "soft lamp", "night sky"],
        "emotion": "soothing, focused", "lighting": "soft dim light",
    },
]
_DEFAULT_PALETTE = {
    "primary": "#7C5CFF", "secondary": "#4ECDFF", "text": "#F5F0E6",
    "subtitle": "smooth music vibes",
    "keywords": ["soft bokeh", "ambient light", "calm scene"],
    "emotion": "smooth, warm", "lighting": "warm light",
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
    light = str(spec.get("lighting", "")).strip()
    if light:
        out["lighting"] = light[:60]
    kws = spec.get("scene_keywords")
    if isinstance(kws, list):
        clean = [str(x).strip() for x in kws if str(x).strip()][:5]
        if clean:
            out["scene_keywords"] = clean
    return out


def _gpt_spec(theme: dict, fallback: dict, *, model: str | None = None) -> dict:
    from services import music_lyrics

    mdl = (model or os.getenv("MUSIC_VIZ_MODEL") or "claude-haiku-4-5-20251001").strip()
    system = (
        "You are an art director for a music video channel. Given a song's metadata, "
        "decide its visual language. Return STRICT JSON only with keys: "
        "primary_color, secondary_color, text_color (all #RRGGBB hex), "
        "subtitle_en (one poetic lowercase english line, 5-8 words), "
        "dominant_emotion (2-3 words), scene_keywords (3-5 short english phrases), "
        "lighting (short english). Colors must match genre/mood; cream/off-white text. "
        "No markdown, no commentary."
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
