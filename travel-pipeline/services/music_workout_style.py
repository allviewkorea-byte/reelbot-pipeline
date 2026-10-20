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
import re as _re

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
    # 2026-10-20 대표 결정: 레퍼런스(청량한 K 댄스팝, 약 160 BPM) 결 위주. 비트를 잘게 쪼개는
    # 트랩·808 하프타임 대신 빠르지만 정박으로 밀고 가는 드럼. 보컬 단어는 넣지 않는다
    # (연주곡에도 같은 부스터가 붙는다 — 성별은 _assign_genders 가 곡별로 정한다).
    "strength": (
        "bright fizzy dance-pop energy, analog synth arpeggios, retro punchy drumline, "
        "steady straight four-on-the-floor kick and snappy snare, electric guitar riffs in the chorus, "
        "refreshing summer hype, gym workout energy, powerful and confident, 150-160 BPM"
    ),
    "cardio": (
        "bright fizzy dance-pop energy, analog synth arpeggios, retro punchy drumline, "
        "steady straight four-on-the-floor kick, propulsive bassline, electric guitar riffs in the chorus, "
        "running cadence, uplifting drive, 150-160 BPM"
    ),
    "warmup": (
        "warm rounded bass, smooth steady groove, clean percussion, "
        "open airy space, focused but relaxed, 90-100 BPM"
    ),
}

# negativeTags - 지금까지 **한 번도 채운 적 없는** 파라미터(music_suno._build_body 는
# 값이 있을 때만 전송한다). AI 스러움·늘어짐을 줄이는 가장 직접적인 수단이다.
# warmup 은 잔잔한 게 정상이라 soft·mellow 를 빼고 '졸린' 쪽만 막는다.
_CHOPPY = "trap hi-hat rolls, glitchy chopped beats, stutter edits, breakbeat, drum and bass, halftime trap"
_NEGATIVE: dict[str, str] = {
    "strength": f"soft, mellow, ambient, lo-fi, sleepy, drowsy, acoustic ballad, slow ballad, {_CHOPPY}",
    "cardio": f"soft, mellow, ambient, lo-fi, sleepy, drowsy, acoustic ballad, slow ballad, {_CHOPPY}",
    "warmup": "sleepy, drowsy, lullaby, droning ambient, sad ballad, gloomy",
}

# 근력·유산소 영상의 첫 장르 — 댄스팝(pop) 위주(대표 결정 70%). 나머지는 풀에서 변화.
MAIN_GENRE = "pop"
MAIN_GENRE_RATE = float((__import__("os").getenv("MUSIC_WORKOUT_MAIN_GENRE_RATE") or "0.7").strip() or 0.7)
# 운동 채널 보컬 성별 — 여성 위주(대표 결정 70%), 나머지는 남성.
FEMALE_RATE = float((__import__("os").getenv("MUSIC_WORKOUT_FEMALE_RATE") or "0.7").strip() or 0.7)


def _pick_genres(pool: list[str], axis: str) -> list[str]:
    """장르 2개. 근력·유산소는 70% 확률로 댄스팝(pop)을 첫 장르로 고정, 둘째는 나머지 풀에서."""
    if axis not in ("strength", "cardio") or MAIN_GENRE not in pool:
        return random.sample(pool, min(2, len(pool)))
    rest = [g for g in pool if g != MAIN_GENRE]
    if random.random() < MAIN_GENRE_RATE:
        return [MAIN_GENRE] + random.sample(rest, min(1, len(rest)))
    return random.sample(rest, min(2, len(rest)))


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
    ax = axis_for_action(combo.get("action"))
    pools = _AXIS_POOLS[ax]
    out = dict(combo)
    for axis, pool in pools.items():
        if not pool:
            continue
        if axis == "genre":
            out[axis] = _pick_genres(pool, ax)
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


# ══════════════════════════════════════════════════════════════════════
# 보컬 곡 장르 고정 · 운동 소재 풀 · 가사 톤 (운동 채널 전용)
#
# 배경(2026-10 실측): 운동 채널 보컬 곡이 "late-night city pop", "mellow city pop" 으로
# 나왔다. 보컬 경로는 가사 플랜 LLM 이 곡별 style 을 새로 짓고(music_lyrics.plan_songs),
# music_produce._gen_vocal 이 그 style 로 태그 style 을 **통째로 대체**한다. 플랜 프롬프트엔
# 장르 정보가 없고 sub-주제 풀이 시티팝 기본값(DEFAULT_SUBTHEME_POOL)이라 LLM 이 시티팝을 짓는다.
#
# ① lock_vocal_style — 태그 style(refine_combo 결과 장르)을 앞에 고정, LLM style 은
#    꼬리 변주로만. 꼬리에서 운동 풀 밖 장르 토큰은 통째로, 처지는 형용사는 단어만 뺀다.
# ② subtheme_pool / lyric_tone — 플랜·작성 단계에 운동 소재와 톤을 넘긴다.
#    warmup(스트레칭) 축은 잔잔한 게 정상이라 톤은 기존 그대로(빈 값), 소재만 맞춘다.
# 기존 함수(refine_combo·boost_style·negative_tags)는 무수정.
# ══════════════════════════════════════════════════════════════════════

SUNO_STYLE_MAX = 1000  # sunoapi style 한도(V4.5+/V6 공통 1000자)

# 운동 풀에 없는 장르 — 토큰에 들어 있으면 그 토큰을 통째로 뺀다("late-night city pop" 등).
# warmup 축 풀에 있는 장르(acoustic·ambient·piano·new age)는 그 축에서만 허용한다.
_FOREIGN_GENRES = (
    "city pop", "citypop", "lo-fi", "lofi", "lo fi", "jazz", "ballad", "acoustic", "ambient",
    "bossa nova", "bossa", "folk", "lounge", "chillhop", "chillwave", "dream pop", "shoegaze",
    "piano ballad", "new age", "classical", "orchestral", "lullaby", "smooth jazz",
)
_WARMUP_ALLOWED_GENRES = ("acoustic", "ambient", "new age", "piano")

# 처지는 형용사 — 토큰은 살리고 단어만 지운다(strength/cardio 기준 목록).
_DROOPY_ALL = (
    "late-night", "late night", "midnight", "mellow", "soft", "chill", "chilled", "laid-back",
    "laid back", "lazy", "slow", "downtempo", "dreamy", "hazy", "muted", "lonely", "wistful",
    "sad", "melancholic", "melancholy", "gloomy", "somber", "sombre", "sleepy", "drowsy", "rainy",
)
# warmup 도 지시 목록(mellow·late-night·soft·chill·sad·melancholic)과 우울 계열은 지운다.
# slow·dreamy·hazy 등 '느긋함' 쪽은 스트레칭 결에 맞을 수 있어 warmup 에선 남긴다.
_DROOPY_WARMUP = (
    "late-night", "late night", "mellow", "soft", "chill", "chilled", "sad", "melancholic",
    "melancholy", "gloomy", "somber", "sombre", "sleepy", "drowsy", "lonely",
)


# 처지는 형용사를 지운 뒤 이것만 남은 토큰은 의미가 없어 버린다("soft vocals" → "vocals").
_FILLER = {"vocals", "vocal", "voice", "groove", "beat", "beats", "sound", "sounds", "vibe", "vibes",
           "warmth", "tone", "tones", "feel", "mood", "texture"}


def _genre_first(tag_style: str) -> str:
    """태그 style 의 장르 토큰을 맨 앞으로(순서만 바꾼다, 내용 동일). "for workout, ..., hip-hop" →
    "hip-hop, for workout, ...". 장르 문구는 music_tags 장르 축 값(전부 단일 토큰)."""
    from services.music_tags import _AXIS_MAP

    genres = {v.lower() for v in (_AXIS_MAP.get("genre") or {}).values()}
    toks = [t.strip() for t in (tag_style or "").split(",") if t.strip()]
    first = [t for t in toks if t.lower() in genres]
    return ", ".join(first + [t for t in toks if t.lower() not in genres])


def _word_re(words) -> "_re.Pattern[str]":
    alts = sorted({w.lower() for w in words}, key=len, reverse=True)
    return _re.compile(r"(?<![a-z])(?:" + "|".join(_re.escape(a) for a in alts) + r")(?![a-z])", _re.I)


def _clean_tail(llm_style: str, axis: str, tag_style: str) -> list[str]:
    """LLM style → 꼬리 토큰 리스트(운동 풀 밖 장르 토큰 제거·처지는 형용사 삭제·중복 제거)."""
    allowed = _WARMUP_ALLOWED_GENRES if axis == "warmup" else ()
    foreign = _word_re([g for g in _FOREIGN_GENRES if g not in allowed])
    droopy = _word_re(_DROOPY_WARMUP if axis == "warmup" else _DROOPY_ALL)
    have = {t.strip().lower() for t in (tag_style or "").split(",") if t.strip()}
    out: list[str] = []
    for tok in (llm_style or "").split(","):
        t = tok.strip()
        if not t or foreign.search(t):
            continue
        t = _re.sub(r"\s{2,}", " ", droopy.sub("", t)).strip(" -/&")
        if len(t) < 3 or t.lower() in _FILLER or t.lower() in have or t.lower() in {x.lower() for x in out}:
            continue
        out.append(t)
    return out


def lock_vocal_style(
    tag_style: str, llm_style: str | None, action: str | None, *, finalize=None,
    channel: str | None = WORKOUT_CHANNEL,
) -> str:
    """운동 채널 보컬 곡 최종 style. 태그 style 이 맨 앞, LLM style(정리본)은 꼬리 변주.

    finalize: 곡별 마무리(성별·명료도 등, music_produce._vocal_style)를 적용하는 함수.
    마무리 + 운동 부스터(boost_style)까지 붙인 **최종 문자열**이 1000자를 넘으면 꼬리를
    뒤에서부터 덜어낸다. where 는 호출하지 않는다(호출부가 채널로 가른다).
    """
    finalize = finalize or (lambda s: s)
    axis = axis_for_action(action)
    head = _genre_first((tag_style or "").strip().strip(",").strip())
    tail = _clean_tail(llm_style or "", axis, head)
    while True:
        body = ", ".join([p for p in [head, *tail] if p])
        style = boost_style(finalize(body), action, channel=channel)
        if len(style) <= SUNO_STYLE_MAX or not tail:
            break
        tail.pop()
    if len(style) > SUNO_STYLE_MAX:  # 꼬리 없이도 넘으면(이론상) 쉼표 경계에서 자른다
        style = style[:SUNO_STYLE_MAX].rsplit(",", 1)[0].strip()
    return style


# 운동 소재 풀(플랜 LLM 참고용 sub-주제). strength/cardio 공용. 대표 검토 대상.
WORKOUT_SUBTHEME_POOL = [
    "마지막 한 세트", "새벽 러닝", "땀으로 젖은 티셔츠", "한계 돌파", "거울 속 나",
    "데드리프트", "숨이 턱까지", "2주 뒤의 나", "포기하고 싶은 순간", "첫 풀업 성공",
    "인터벌 마지막 바퀴", "빈 헬스장의 새벽", "어제보다 1kg 더", "결승선 직전", "끝까지 버틴 나",
]
# warmup(스트레칭·요가·명상 등) 축 — 근력 소재는 결이 안 맞아 몸 풀기 소재로 따로.
WORKOUT_WARMUP_SUBTHEME_POOL = [
    "아침 스트레칭", "굳은 어깨 풀기", "깊은 호흡", "몸이 깨어나는 순간", "운동 전 워밍업",
    "쿨다운", "매트 위의 고요", "오늘도 나를 돌보는 시간",
]
WORKOUT_LYRIC_TONE = "신나고 힘 있는, 자신감·성취감. 느리거나 우울한 정서 금지."


def subtheme_pool(action: str | None, *, channel: str | None = None) -> list[str] | None:
    """플랜 단계 sub-주제 풀. 운동 채널이 아니면 None(→ 기존 기본 풀 그대로)."""
    if not is_workout_channel(channel):
        return None
    return list(WORKOUT_WARMUP_SUBTHEME_POOL if axis_for_action(action) == "warmup" else WORKOUT_SUBTHEME_POOL)


def lyric_tone(action: str | None, *, channel: str | None = None) -> str | None:
    """작성 단계 가사 톤. 운동 채널 strength/cardio 만 운동 톤, 그 외 None(→ 기존 값 유지)."""
    if not is_workout_channel(channel) or axis_for_action(action) == "warmup":
        return None
    return WORKOUT_LYRIC_TONE
