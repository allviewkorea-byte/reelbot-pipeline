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
    "baby_sleep": {"label_kr": "아기재울때", "prompt_en": "for putting a baby to sleep, gentle lullaby, music box"},
    "focus": {"label_kr": "집중할때", "prompt_en": "for deep focus, concentration"},
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
    "music_box": "music box, lullaby chime", "white_noise": "ambient white noise, soft background texture",
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

# ── 한글 라벨 (제목·해시태그용) ──────────────────────────────────────
_GENRE_KR: dict[str, str] = {
    "citypop": "시티팝", "lofi": "로파이", "jazz": "재즈", "acoustic": "어쿠스틱",
    "piano": "피아노", "rnb": "알앤비", "ballad": "발라드", "pop": "팝",
    "indie": "인디", "bossanova": "보사노바", "ambient": "앰비언트",
    "classical": "클래식", "electronic": "일렉트로닉", "synthwave": "신스웨이브",
    "soul": "소울", "neosoul": "네오소울", "dreampop": "드림팝",
    "hiphop": "힙합", "lofihiphop": "로파이힙합", "chillhop": "칠합",
    "triphop": "트립합", "house": "하우스", "deephouse": "딥하우스",
    "jazzhop": "재즈합", "newage": "뉴에이지", "kindie": "K인디",
    "kballad": "K발라드", "sensballad": "감성발라드",
}
_SITUATION_KR: dict[str, str] = {
    "rain": "비올때", "snow": "눈올때", "sunny": "맑은날", "cloudy": "흐린날",
    "first_snow": "첫눈", "spring": "봄", "summer": "여름", "autumn": "가을",
    "winter": "겨울", "breakup": "이별", "meeting": "만남", "confession": "고백",
    "alone": "혼자일때", "window": "창밖", "lights_off": "불끄고누웠을때",
}
_EMOTION_KR: dict[str, str] = {
    "lonely": "외로움", "sad": "슬픔", "nostalgic": "그리움", "depressed": "우울",
    "desolate": "쓸쓸함", "happy": "기분좋음", "refreshed": "기분전환",
    "excited": "설렘", "heartbeat": "두근거림", "positive": "긍정", "hopeful": "희망",
    "passionate": "열정", "calm": "차분함", "peaceful": "평온", "drowsy": "나른함",
    "dreamy": "몽환", "comfort": "위로", "warm": "따뜻함",
    "overwhelmed": "벅참", "free": "자유로움", "sentimental": "센치함",
}
_TEMPO_KR: dict[str, str] = {
    "gentle": "잔잔한", "slow": "느린", "relaxed": "편안한", "moderate": "적당한",
    "lively": "경쾌한", "upbeat": "신나는", "fast": "빠른", "intense": "강렬한",
}
_CHARM_KR: dict[str, str] = {
    "melody": "멜로디가인상적인", "beat": "비트가매력적인",
    "addictive": "중독성있는", "refined": "세련된",
    "immersive": "편안하게빠져드는", "emotional": "감성을자극하는",
    "refreshing": "청량한", "deep": "깊이있는",
}
_AXIS_KR: dict[str, dict[str, str]] = {
    "genre": _GENRE_KR, "situation": _SITUATION_KR, "emotion": _EMOTION_KR,
    "tempo": _TEMPO_KR, "charm": _CHARM_KR,
}

# ── 충돌 규칙 ─────────────────────────────────────────────────────────
_CALM = {"sleep", "meditation", "rest", "yoga", "stretching", "pilates", "baby_sleep"}
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
    if action_id == "focus":
        hidden["tempo"] = {"intense", "fast"}
        hidden["charm"] = {"addictive"}
    if action_id == "singing":
        hidden["format"] = {"instrumental", "inst_only", "nature_only", "beats_only"}
    return hidden


# ── Suno style 문자열 변환 ─────────────────────────────────────────
_SLEEP_STYLE_BOOST = "soothing, calm, for sleep, gentle, soft, slow"
_SLEEP_VOCAL_BOOST = "slow ballad, whisper-like vocals, lullaby feel"
_BABY_SLEEP_STYLE_BOOST = "lullaby, music box, very gentle, soft, slow, soothing baby sleep"
_FOCUS_STYLE_BOOST = "focus-enhancing, steady rhythm, minimal distraction, concentration"


def tags_to_suno_style(combo: dict) -> str:
    """TagCombo dict → Suno style 문자열(쉼표 구분).

    combo 예: {"action": "study", "genre": ["lofi", "jazz"], "emotion": ["calm"], ...}
    반환 예: "for studying, focus, lo-fi, jazz, calm, composed, gentle, soft"

    잠들때(action=sleep): 잠들때 맥락 키워드 강화 주입(신나는 곡 방지).
    보컬곡이면 slow ballad 톤도 추가.
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
    if action_id == "sleep":
        parts.append(_SLEEP_STYLE_BOOST)
        if not is_instrumental(combo):
            parts.append(_SLEEP_VOCAL_BOOST)
    elif action_id == "baby_sleep":
        parts.append(_BABY_SLEEP_STYLE_BOOST)
    elif action_id == "focus":
        parts.append(_FOCUS_STYLE_BOOST)
    return ", ".join(parts)


def combo_labels_kr(combo: dict) -> dict[str, list[str]]:
    """TagCombo → 축별 한글 라벨 목록. 제목·해시태그·프롬프트 생성용."""
    result: dict[str, list[str]] = {}
    action_id = combo.get("action")
    if action_id and action_id in ACTION_TAGS:
        result["action"] = [ACTION_TAGS[action_id]["label_kr"]]
    for axis in ("genre", "situation", "emotion", "tempo", "charm"):
        kr_map = _AXIS_KR.get(axis, {})
        ids = combo.get(axis) or []
        if isinstance(ids, str):
            ids = [ids]
        labels = [kr_map[tid] for tid in ids if tid in kr_map]
        if labels:
            result[axis] = labels
    return result


def combo_summary_kr(combo: dict) -> str:
    """TagCombo → 한국어 한 줄 요약. 예: '명상할때 · 어쿠스틱 · 비올때 · 차분함'"""
    labels = combo_labels_kr(combo)
    parts: list[str] = []
    for axis in ("action", "genre", "situation", "emotion", "tempo", "charm"):
        for lbl in labels.get(axis, []):
            parts.append(lbl)
    return " · ".join(parts[:6])


def is_instrumental(combo: dict) -> bool:
    """format 축에 instrumental 계열이 있으면 True.

    잠들때(action=sleep) 특칙: 보컬 명시("vocal")가 없으면 연주곡(True).
    format 미선택 or nature_mix 등 비보컬 → 연주곡. "vocal" 선택 시에만 보컬 허용.
    """
    fmt = combo.get("format") or []
    if isinstance(fmt, str):
        fmt = [fmt]
    if set(fmt) & {"instrumental", "inst_only", "piano_solo", "guitar_solo", "beats_only", "nature_only", "music_box", "white_noise"}:
        return True
    # 잠들때/아기재울때/집중할때: 보컬 명시 없으면 연주곡 확정(보컬 누수 방지).
    if combo.get("action") in ("sleep", "baby_sleep", "focus") and "vocal" not in fmt:
        return True
    return False


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
    {"action": "baby_sleep", "genre": ["classical", "piano"], "emotion": ["warm"], "tempo": ["gentle"], "format": ["music_box"]},
    {"action": "focus", "genre": ["lofi", "ambient"], "emotion": ["calm"], "tempo": ["moderate"]},
]


_SLEEP_DEFAULTS: dict[str, list[str]] = {
    "genre": ["ballad", "piano", "acoustic", "ambient", "classical", "newage", "sensballad"],
    "tempo": ["gentle", "slow", "relaxed"],
    "emotion": ["calm", "peaceful", "drowsy", "warm", "comfort", "lonely", "sad", "nostalgic", "dreamy"],
}

_BABY_SLEEP_DEFAULTS: dict[str, list[str]] = {
    "genre": ["classical", "piano", "acoustic", "ambient", "newage"],
    "tempo": ["gentle", "slow"],
    "emotion": ["warm", "peaceful", "calm", "dreamy", "comfort"],
    "format": ["music_box", "instrumental", "piano_solo"],
}

_FOCUS_DEFAULTS: dict[str, list[str]] = {
    "genre": ["lofi", "ambient", "lofihiphop", "chillhop", "jazzhop", "piano", "classical", "electronic"],
    "tempo": ["moderate", "relaxed", "gentle"],
    "emotion": ["calm", "peaceful"],
}


def smart_random(partial: dict | None = None) -> dict:
    """빈 축을 맥락에 맞게 자동 채움.

    partial 이 주어지면 이미 선택된 축은 유지, 빈 축만 프리셋 기반으로 채운다.
    partial 이 없으면 프리셋 중 하나를 랜덤 선택.
    잠들때(action=sleep): 미선택 장르·템포·감정을 잠들때 어울리는 풀에서 채움.
    """
    if not partial or not any(partial.values()):
        return dict(random.choice(_RANDOM_PRESETS))

    result = dict(partial)
    hidden = conflict_hidden_chips(result.get("action"))
    action = result.get("action")
    action_defaults = (
        _SLEEP_DEFAULTS if action == "sleep"
        else _BABY_SLEEP_DEFAULTS if action == "baby_sleep"
        else _FOCUS_DEFAULTS if action == "focus"
        else None
    )

    for axis, tags_map in _AXIS_MAP.items():
        existing = result.get(axis)
        if existing:
            continue
        hidden_ids = hidden.get(axis, set())
        if action_defaults and axis in action_defaults:
            pool = [k for k in action_defaults[axis] if k in tags_map and k not in hidden_ids]
            if pool:
                pick_count = 1 if axis in ("tempo",) else random.randint(1, 2)
                result[axis] = random.sample(pool, min(pick_count, len(pool)))
                continue
        candidates = [k for k in tags_map if k not in hidden_ids]
        if not candidates:
            continue
        pick_count = 1 if axis in ("tempo", "format") else random.randint(1, 2)
        result[axis] = random.sample(candidates, min(pick_count, len(candidates)))

    return result
