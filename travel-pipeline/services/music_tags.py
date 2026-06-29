"""8축 태그 풀 SSOT — 백엔드 (#③-A).

프론트엔드: src/lib/music-tags.ts (동일 구조, 둘 다 갱신).
태그 조합 → Suno style 문자열 변환 + 똑똑한 랜덤(빈 축 자동 채움).
"""

from __future__ import annotations

import random

# ── 축1 어떨때(행동) — 메인 드롭다운 ────────────────────────────────
ACTION_TAGS: dict[str, dict] = {
    "study": {"label_kr": "공부할때", "prompt_en": "for studying, focus"},
    "work": {"label_kr": "일할때", "prompt_en": "for working, productivity"},
    "workout": {"label_kr": "운동할때", "prompt_en": "for workout, energetic"},
    "running": {"label_kr": "러닝할때", "prompt_en": "for running, high energy"},
    "sleep": {"label_kr": "잠들때", "prompt_en": "for sleep, soothing lullaby"},
    "rest": {"label_kr": "휴식할때", "prompt_en": "for relaxation, unwinding"},
    "drive": {"label_kr": "운전할때", "prompt_en": "for driving, cruising"},
    "drive_scenic": {"label_kr": "드라이브할때", "prompt_en": "for scenic drive, road trip"},
    "commute_morning": {"label_kr": "출근할때", "prompt_en": "morning commute, uplifting start"},
    "commute_evening": {"label_kr": "퇴근할때", "prompt_en": "evening commute, unwinding"},
    "cafe": {"label_kr": "카페에서", "prompt_en": "cafe ambience, coffee shop"},
    "walk": {"label_kr": "산책할때", "prompt_en": "for a walk, strolling"},
    "cleaning": {"label_kr": "청소할때", "prompt_en": "for cleaning, upbeat chores"},
    "cooking": {"label_kr": "요리할때", "prompt_en": "for cooking, kitchen vibes"},
    "shower": {"label_kr": "샤워할때", "prompt_en": "for shower, sing-along"},
    "reading": {"label_kr": "독서할때", "prompt_en": "for reading, quiet focus"},
    "coding": {"label_kr": "코딩할때", "prompt_en": "for coding, deep focus"},
    "meditation": {"label_kr": "명상할때", "prompt_en": "for meditation, mindfulness"},
    "date": {"label_kr": "데이트할때", "prompt_en": "for a date, romantic"},
    "singing": {"label_kr": "노래하고싶을때", "prompt_en": "sing-along, karaoke vibe"},
    "swimming": {"label_kr": "물놀이할때", "prompt_en": "for swimming, summer pool"},
    "pet": {"label_kr": "애견과함께있을때", "prompt_en": "with pets, gentle and warm"},
    "couple": {"label_kr": "남친여친과함께있을때", "prompt_en": "with significant other, romantic"},
    "startup": {"label_kr": "창업할때", "prompt_en": "for entrepreneurship, motivational"},
    "zone_out": {"label_kr": "멍때리고싶을때", "prompt_en": "zoning out, ambient drift"},
    "confidence": {"label_kr": "자신감얻고싶을때", "prompt_en": "for confidence boost, empowering"},
    "hungry": {"label_kr": "배고플때", "prompt_en": "feeling hungry, fun and playful"},
    "full": {"label_kr": "배부를때", "prompt_en": "after a meal, cozy and satisfied"},
    "stretching": {"label_kr": "스트레칭할때", "prompt_en": "for stretching, gentle flow"},
    "pilates": {"label_kr": "필라테스할때", "prompt_en": "for pilates, controlled tempo"},
    "yoga": {"label_kr": "요가할때", "prompt_en": "for yoga, serene and balanced"},
}

# ── 축2~8 (칩 기반) ──────────────────────────────────────────────────
GENRE_TAGS: dict[str, str] = {
    "citypop": "city pop", "lofi": "lo-fi", "jazz": "jazz", "acoustic": "acoustic",
    "piano": "piano", "rnb": "R&B", "ballad": "ballad", "pop": "pop",
    "indie": "indie", "bossanova": "bossa nova", "ambient": "ambient",
    "classical": "classical", "electronic": "electronic", "synthwave": "synthwave",
    "soul": "soul", "neosoul": "neo soul", "dreampop": "dream pop",
    "hiphop": "hip-hop", "lofihiphop": "lo-fi hip-hop", "chillhop": "chill hop",
    "triphop": "trip-hop", "house": "house", "deephouse": "deep house",
    "jazzhop": "jazz hop", "newage": "new age", "kindie": "Korean indie",
    "kballad": "Korean ballad", "sensballad": "emotional ballad",
}

SITUATION_TAGS: dict[str, str] = {
    "rain": "rainy day", "snow": "snowy day", "sunny": "sunny day",
    "cloudy": "cloudy day", "first_snow": "first snow",
    "spring": "spring", "summer": "summer", "autumn": "autumn", "winter": "winter",
    "breakup": "breakup, farewell", "meeting": "meeting someone",
    "confession": "confession, first love", "alone": "alone, solitude",
    "window": "looking out the window", "lights_off": "lying in the dark",
}

EMOTION_TAGS: dict[str, str] = {
    "lonely": "lonely", "sad": "sad", "nostalgic": "nostalgic, longing",
    "depressed": "melancholic", "desolate": "desolate",
    "happy": "happy, feel good", "refreshed": "mood refresh, uplifting",
    "excited": "excited, fluttering", "heartbeat": "heart-pounding",
    "positive": "positive, optimistic", "hopeful": "hopeful, inspiring",
    "passionate": "passionate, fiery", "calm": "calm, composed",
    "peaceful": "peaceful, serene", "drowsy": "drowsy, lazy",
    "dreamy": "dreamy, ethereal", "comfort": "comforting, consoling",
    "warm": "warm, heartwarming", "overwhelmed": "overwhelmed with emotion",
    "free": "free, liberating", "sentimental": "sentimental",
}

TEMPO_TAGS: dict[str, str] = {
    "gentle": "gentle, soft", "slow": "slow tempo", "relaxed": "relaxed",
    "moderate": "moderate tempo", "lively": "lively, bouncy",
    "upbeat": "upbeat, exciting", "fast": "fast tempo", "intense": "intense, powerful",
}

FORMAT_TAGS: dict[str, str] = {
    "vocal": "with vocals", "instrumental": "instrumental, no lyrics",
    "piano_solo": "piano solo", "guitar_solo": "acoustic guitar solo",
    "inst_only": "pure instrumental", "beats_only": "beats only, no vocals",
    "nature_mix": "nature sounds mixed with music", "nature_only": "nature sounds only, no music",
}

CHARM_TAGS: dict[str, str] = {
    "melody": "memorable melody", "beat": "attractive beat",
    "addictive": "addictive, catchy", "refined": "refined, sophisticated",
    "immersive": "immersive, easy listening", "emotional": "emotionally evocative",
    "refreshing": "refreshing, crisp", "deep": "deep, profound",
}

_AXIS_MAP: dict[str, dict[str, str]] = {
    "genre": GENRE_TAGS, "situation": SITUATION_TAGS, "emotion": EMOTION_TAGS,
    "tempo": TEMPO_TAGS, "format": FORMAT_TAGS, "charm": CHARM_TAGS,
}

# ── 충돌 규칙 ─────────────────────────────────────────────────────────
_CALM = {"sleep", "meditation", "rest", "yoga", "stretching", "pilates"}
_INTENSE = {"workout", "running", "confidence"}


def conflict_hidden_chips(action_id: str | None) -> dict[str, set[str]]:
    """행동에 따라 숨길 칩 id 집합 반환."""
    if not action_id:
        return {}
    hidden: dict[str, set[str]] = {}
    if action_id in _CALM:
        hidden["tempo"] = {"intense", "fast", "upbeat"}
        hidden["charm"] = {"addictive", "beat"}
    if action_id in _INTENSE:
        hidden["tempo"] = {"gentle", "slow"}
    if action_id == "meditation":
        hidden["format"] = {k for k in FORMAT_TAGS if k != "instrumental"}
    if action_id == "singing":
        hidden["format"] = {"instrumental", "inst_only", "nature_only", "beats_only"}
    return hidden


# ── Suno style 문자열 변환 ─────────────────────────────────────────
def tags_to_suno_style(combo: dict) -> str:
    """TagCombo dict → Suno style 문자열(쉼표 구분).

    combo 예: {"action": "study", "genre": ["lofi", "jazz"], "emotion": ["calm"], ...}
    반환 예: "for studying, focus, lo-fi, jazz, calm, composed, gentle, soft"
    """
    parts: list[str] = []
    action_id = combo.get("action")
    if action_id and action_id in ACTION_TAGS:
        parts.append(ACTION_TAGS[action_id]["prompt_en"])
    for axis in ("genre", "situation", "emotion", "tempo", "format", "charm"):
        tags_map = _AXIS_MAP.get(axis, {})
        ids = combo.get(axis) or []
        if isinstance(ids, str):
            ids = [ids]
        for tid in ids:
            prompt = tags_map.get(tid)
            if prompt:
                parts.append(prompt)
    return ", ".join(parts)


def is_instrumental(combo: dict) -> bool:
    """format 축에 instrumental 계열이 있으면 True."""
    fmt = combo.get("format") or []
    if isinstance(fmt, str):
        fmt = [fmt]
    return bool(set(fmt) & {"instrumental", "inst_only", "piano_solo", "guitar_solo", "beats_only", "nature_only"})


# ── 똑똑한 랜덤 ──────────────────────────────────────────────────────
_RANDOM_PRESETS: list[dict] = [
    {"action": "study", "genre": ["lofi"], "emotion": ["calm"], "tempo": ["gentle"]},
    {"action": "drive", "genre": ["citypop"], "emotion": ["happy"], "tempo": ["moderate"]},
    {"action": "rest", "genre": ["jazz", "acoustic"], "emotion": ["peaceful"], "tempo": ["relaxed"]},
    {"action": "workout", "genre": ["electronic"], "emotion": ["passionate"], "tempo": ["fast"]},
    {"action": "sleep", "genre": ["ambient", "piano"], "emotion": ["drowsy"], "tempo": ["gentle"]},
    {"action": "cafe", "genre": ["bossanova", "acoustic"], "emotion": ["warm"], "tempo": ["relaxed"]},
    {"action": "date", "genre": ["rnb", "neosoul"], "emotion": ["excited"], "tempo": ["moderate"]},
    {"action": "walk", "genre": ["indie", "dreampop"], "emotion": ["free"], "tempo": ["lively"]},
    {"action": "coding", "genre": ["lofihiphop"], "emotion": ["calm"], "tempo": ["moderate"]},
    {"action": "meditation", "genre": ["ambient", "newage"], "emotion": ["peaceful"], "tempo": ["gentle"], "format": ["instrumental"]},
]


def smart_random(partial: dict | None = None) -> dict:
    """빈 축을 맥락에 맞게 자동 채움.

    partial 이 주어지면 이미 선택된 축은 유지, 빈 축만 프리셋 기반으로 채운다.
    partial 이 없으면 프리셋 중 하나를 랜덤 선택.
    """
    if not partial or not any(partial.values()):
        return dict(random.choice(_RANDOM_PRESETS))

    result = dict(partial)
    hidden = conflict_hidden_chips(result.get("action"))

    for axis, tags_map in _AXIS_MAP.items():
        existing = result.get(axis)
        if existing:
            continue
        hidden_ids = hidden.get(axis, set())
        candidates = [k for k in tags_map if k not in hidden_ids]
        if not candidates:
            continue
        pick_count = 1 if axis in ("tempo", "format") else random.randint(1, 2)
        result[axis] = random.sample(candidates, min(pick_count, len(candidates)))

    return result
