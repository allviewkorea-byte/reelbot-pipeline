"""운동 채널 전용 스타일 보정 — 태그 보정 · Suno style 부스터 · negativeTags (5단계 B).

배경: "운동할때" 하나만 고르면 music_tags.smart_random 이 빈 축을 **균등 랜덤**으로
채운다. action별 기본값이 sleep·baby_sleep·focus 셋뿐이라 workout·running 은
`dream pop, lying in the dark, peaceful, serene` 같은 정반대 태그를 뽑는다(실측 확인).
그 상태로는 style 문자열을 아무리 다듬어도 헬스장 음악이 나오지 않는다.

이 모듈은 **운동 채널일 때만** 개입한다:
  ① refine_combo  — smart_random 이 지어낸 축을 운동에 맞는 풀로 교체(대표 선택은 보존)
  ② boost_style   — Suno style 뒤에 구체적 음악 용어를 덧붙임(LLM style 은 버리지 않음)
  ③ negative_tags — Suno negativeTags(지금까지 아무도 안 채우던 파라미터)

★ music_tags.py 는 수정하지 않는다. 태그 **풀에 이미 있는 id 중에서만** 고른다.
   (락·펑크·트랩·EDM 태그 추가는 다음 작업)
★ where(미지정 포함)는 이 모듈을 한 줄도 타지 않는다 — 호출부가 전부 채널로 가른다.
"""

from __future__ import annotations

import random

# 이 모듈이 개입하는 채널. 다른 채널이 생기면 여기부터 넓힌다.
WORKOUT_CHANNEL = "workout_music"

# action -> 축. 4단계 재생목록 매핑(youtube_upload._WORKOUT_ACTION_MAP)과 **같은 축**이다.
# 영상·재생목록·이미지·음악이 한 덩어리로 움직이게 하려는 의도적 중복.
ACTION_AXIS: dict[str, str] = {
    "workout": "strength", "confidence": "strength",
    "running": "cardio", "swimming": "cardio",
    "stretching": "warmup", "yoga": "warmup", "pilates": "warmup",
    "meditation": "warmup", "rest": "warmup", "walk": "warmup",
}
DEFAULT_AXIS = "strength"  # 미매핑 action 폴백. None 이면 where 결로 새어버린다.

# 축별 태그 풀 - 전부 music_tags 에 **이미 존재하는 id** 다.
# ※ GENRE_TAGS 에 rock 계열이 없다(락·펑크·트랩·EDM 는 다음 작업의 태그 풀 추가 대상).
#   지금은 hiphop·electronic·house·synthwave·pop 으로 "강렬한 비트"를 만든다.
# ※ EMOTION_TAGS 에 'energetic' id 는 없다("energetic" 문구는 ACTION_TAGS 에서 나온다).
#   대신 passionate·excited·heartbeat·positive·free 를 쓴다.
_AXIS_POOLS: dict[str, dict[str, list[str]]] = {
    "strength": {
        "genre": ["hiphop", "electronic", "house", "synthwave", "triphop", "pop"],
        "emotion": ["passionate", "excited", "heartbeat", "positive", "free"],
        "tempo": ["fast", "intense", "upbeat"],
        "situation": ["sunny", "summer"],
        "charm": ["beat", "addictive", "melody"],
    },
    "cardio": {
        "genre": ["electronic", "house", "deephouse", "hiphop", "synthwave", "pop"],
        "emotion": ["refreshed", "excited", "hopeful", "free", "positive"],
        "tempo": ["fast", "upbeat", "lively"],
        "situation": ["sunny", "summer", "spring"],
        "charm": ["beat", "refreshing", "addictive"],
    },
    # 스트레칭·요가·명상은 워밍업/쿨다운이다. 여기까지 808 을 때리면 결이 깨진다 -
    # "잔잔하지만 늘어지지 않는" 중간 템포로 잡는다.
    "warmup": {
        "genre": ["house", "electronic", "piano", "acoustic", "newage", "ambient"],
        "emotion": ["calm", "refreshed", "positive", "warm", "hopeful"],
        "tempo": ["moderate", "relaxed", "lively"],
        "situation": ["sunny", "spring"],
        "charm": ["melody", "immersive", "refreshing"],
    },
}

# Suno style 뒤에 붙는 구체 음악 용어. GENRE_TAGS 한 단어("hip-hop")로는
# 평균적인 결과만 나온다 - v5.5 는 긴 프롬프트·풍부한 스타일 태그를 받는다.
_STYLE_BOOST: dict[str, str] = {
    "strength": (
        "hard-hitting drums, punchy 808 bass, gritty texture, driving groove, "
        "gym workout energy, powerful and confident, 95-105 BPM"
    ),
    "cardio": (
        "steady four-on-the-floor kick, propulsive bassline, bright synth hooks, "
        "running cadence, high energy, uplifting drive, 150-165 BPM"
    ),
    "warmup": (
        "warm rounded bass, smooth steady groove, clean percussion, "
        "open airy space, focused but relaxed, 90-100 BPM"
    ),
}

# negativeTags - 지금까지 **한 번도 채운 적 없는** 파라미터(music_suno._build_body 는
# 값이 있을 때만 전송한다). AI 스러움·늘어짐을 줄이는 가장 직접적인 수단이다.
# warmup 은 잔잔한 게 정상이라 soft·mellow 를 빼고 '졸린' 쪽만 막는다.
_NEGATIVE: dict[str, str] = {
    "strength": "soft, mellow, ambient, lo-fi, sleepy, drowsy, acoustic ballad, slow ballad",
    "cardio": "soft, mellow, ambient, lo-fi, sleepy, drowsy, acoustic ballad, slow ballad",
    "warmup": "sleepy, drowsy, lullaby, droning ambient, sad ballad, gloomy",
}


def is_workout_channel(channel: str | None) -> bool:
    """운동 채널인가. None·where·미등록 → False(기존 동작 그대로)."""
    return isinstance(channel, str) and channel.strip() == WORKOUT_CHANNEL


def axis_for_action(action: str | None) -> str:
    """action → strength/cardio/warmup. 미매핑·빈값 → strength."""
    return ACTION_AXIS.get((action or "").strip(), DEFAULT_AXIS)


def refine_combo(combo: dict | None, *, channel: str | None = None) -> dict | None:
    """smart_random 이 채운 축을 운동에 맞는 풀로 교체한다.

    **대표가 직접 고른 칩이 있으면 부르지 않는다** — 호출부가 "칩이 하나도 없어서
    smart_random 을 돌린" 경우에만 부른다. format 축은 손대지 않는다(보컬·연주 둘 다
    허용 + meditation 등 연주곡 고정 action 의 기존 규칙 보존).
    운동 채널이 아니거나 combo 가 비면 원본을 그대로 돌려준다(회귀 0).
    """
    if not is_workout_channel(channel) or not isinstance(combo, dict) or not combo:
        return combo
    pools = _AXIS_POOLS[axis_for_action(combo.get("action"))]
    out = dict(combo)
    for axis, pool in pools.items():
        if not pool:
            continue
        pick = 1 if axis in ("tempo", "situation") else min(2, len(pool))
        out[axis] = random.sample(pool, min(pick, len(pool)))
    return out


def style_booster(action: str | None, *, channel: str | None = None) -> str:
    """Suno style 뒤에 붙일 구체 음악 용어. 운동 채널이 아니면 빈 문자열."""
    if not is_workout_channel(channel):
        return ""
    return _STYLE_BOOST[axis_for_action(action)]


def boost_style(style: str, action: str | None, *, channel: str | None = None) -> str:
    """style + 부스터. 원본 style(LLM 이 지은 곡별 변주)은 **버리지 않고 뒤에 붙인다**.

    이미 부스터가 붙어 있으면 그대로(중복 방지). where 는 인자 그대로 반환.
    """
    boost = style_booster(action, channel=channel)
    if not boost:
        return style
    base = (style or "").strip().strip(",").strip()
    if boost in base:
        return base
    return f"{base}, {boost}" if base else boost


def negative_tags(action: str | None, *, channel: str | None = None) -> str | None:
    """Suno negativeTags. 운동 채널이 아니면 None → music_suno 가 전송하지 않는다."""
    if not is_workout_channel(channel):
        return None
    return _NEGATIVE[axis_for_action(action)]
