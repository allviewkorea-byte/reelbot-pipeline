"""YouTube 메타데이터 풍부화(#37) — 제목·본문·해시태그 자동 생성.

글로벌 음악 채널 SEO·시청자 경험: 𝐏𝐥𝐚𝐲𝐥𝐢𝐬𝐭 시그니처 제목, 본문(감성 멘트 +
트랙리스트 + 고정 정보), 30~50개 해시태그. 제목 후킹 카피와 감성 멘트는 LLM 생성
(실패 시 결정적 풀 폴백). 다국어 번역은 music_translate 가 이 결과를 입력으로 받아
처리(공개 업로드 단계에서만).

빈 슬로건·소셜은 해당 줄/섹션을 출력하지 않는다(조건부 분기). viz_spec 이 없거나
키가 비어도 안전 기본으로 동작한다.
"""

from __future__ import annotations

import logging
import os
import re

from services import music_genres  # #52-E 장르 영문 라벨(label_en) — 19장르 정확 표기

logger = logging.getLogger(__name__)


def _has_tag_combo(theme: dict) -> bool:
    return bool(theme.get("tag_combo"))

# 𝐏𝐥𝐚𝐲𝐥𝐢𝐬𝐭 — Unicode Mathematical Bold(모든 영상 공통 시그니처). 일반 'Playlist' 와 다른 코드포인트.
SIGNATURE = "\U0001D40F\U0001D425\U0001D41A\U0001D432\U0001D425\U0001D422\U0001D42C\U0001D42D"
SEP = "━" * 20


def _channel_name() -> str:
    return (os.getenv("MUSIC_CHANNEL_NAME") or os.getenv("NEXT_PUBLIC_MUSIC_CHANNEL_NAME") or "Revezen").strip()


def _pick(pool: list[str], seed: str) -> str:
    """seed(슬러그 등) 기반 결정적 선택 — 같은 영상은 항상 같은 카피."""
    if not pool:
        return ""
    h = sum(ord(c) for c in (seed or "x"))
    return pool[h % len(pool)]


# ── 장르/이모지/용도/플래그 매핑(결정적) ──────────────────────────────
def genre_en(theme: dict, vs: dict) -> str:
    """한국어 장르/스타일 → 영문 슬러그(citypop/lofi/jazz/pop/acoustic)."""
    text = " ".join([
        str(theme.get("genre") or ""), str(theme.get("style_prompt") or ""),
        str(vs.get("subtitle_en") or ""),
    ]).lower()
    if "citypop" in text or "city pop" in text or "시티팝" in text:
        return "city pop"
    if "lofi" in text or "lo-fi" in text or "로파이" in text or "lo fi" in text:
        return "lofi"
    if "jazz" in text or "재즈" in text:
        return "jazz"
    if "acoustic" in text or "어쿠스틱" in text or "포크" in text or "folk" in text:
        return "acoustic"
    return "pop"


def _emoji(theme: dict, vs: dict) -> str:
    """무드/장소/장르 → 대표 이모지. 🌃 🌊 ☕ 🌙 ☀️."""
    g = genre_en(theme, vs)
    loc = str(vs.get("location_category") or "").lower()
    mood = str(vs.get("mood_category") or "").lower()
    season = str(vs.get("season") or "").lower()
    situ = str(theme.get("situation") or "")
    if loc == "beach" or season == "summer":
        return "🌊"
    if g == "jazz" or loc == "cafe" or "카페" in situ:
        return "☕"
    if g == "lofi" or mood in ("sleep", "focus") or "수면" in situ or "공부" in situ:
        return "🌙"
    if mood == "energetic" or "운동" in situ or "출근" in situ:
        return "☀️"
    return "🌃"


_PURPOSE_BY_GENRE: dict[str, list[str]] = {
    "city pop": ["작업용", "카페음악"],
    "lofi": ["휴식", "수면음악"],
    "jazz": ["카페", "집중음악"],
    "acoustic": ["휴식", "감성음악"],
    "pop": ["운동", "노동요"],
}


def _purposes(theme: dict, vs: dict) -> list[str]:
    """용도(한국어) 1~2개. 상황 키워드가 있으면 우선 반영."""
    situ = str(theme.get("situation") or "")
    mood = str(vs.get("mood_category") or "").lower()
    out: list[str] = []
    if "수면" in situ or "잠" in situ or mood == "sleep":
        out = ["수면음악", "휴식"]
    elif "공부" in situ or "집중" in situ or mood == "focus":
        out = ["집중음악", "공부"]
    elif "운동" in situ:
        out = ["운동", "노동요"]
    elif "카페" in situ:
        out = ["카페음악", "작업용"]
    elif "출근" in situ or "출퇴근" in situ or "드라이브" in situ:
        out = ["작업용", "출퇴근"]
    if not out:
        out = list(_PURPOSE_BY_GENRE.get(genre_en(theme, vs), ["작업용", "카페음악"]))
    return out[:2]


_FLAGS: list[tuple[tuple[str, ...], str]] = [
    (("new york", "newyork", "manhattan", "brooklyn", "usa", "america"), "🇺🇸"),
    (("tokyo", "japan", "shibuya", "osaka"), "🇯🇵"),
    (("paris", "france"), "🇫🇷"),
    (("seoul", "korea", "한강", "busan"), "🇰🇷"),
    (("london", "uk", "britain"), "🇬🇧"),
    (("hawaii", "california", "coast", "beach", "miami"), "🏝️"),
]


def _flag(vs: dict) -> str:
    loc = str(vs.get("location_en") or "").lower()
    for keys, flag in _FLAGS:
        if any(k in loc for k in keys):
            return flag
    return "🌍"


# ── 감정 카피(한국어, 결정적 풀) ──────────────────────────────────────
_COPY_POOL: dict[str, list[str]] = {
    "city pop": [
        "새벽 도시를 달리며 듣는 시티팝", "네온 불빛 사이를 걷는 시티팝",
        "퇴근길 창밖을 바라보며 듣는 시티팝",
    ],
    "lofi": [
        "잠들기 전 마음을 정돈하는 lo-fi", "비 오는 밤 혼자 듣는 로파이",
        "집중이 필요한 순간의 로파이",
    ],
    "jazz": [
        "비 오는 카페에서 듣는 재즈", "늦은 밤 와인 한 잔과 듣는 재즈",
        "여유로운 주말 아침의 재즈",
    ],
    "acoustic": [
        "햇살 좋은 오후에 듣는 어쿠스틱", "산책하며 듣는 따뜻한 어쿠스틱",
        "창가에 앉아 듣는 어쿠스틱",
    ],
    "pop": [
        "기분 전환이 필요할 때 듣는 팝", "에너지가 필요한 순간의 팝송",
        "오늘 하루를 응원하는 팝",
    ],
}


def _copy(theme: dict, vs: dict) -> str:
    return _pick(_COPY_POOL.get(genre_en(theme, vs), _COPY_POOL["pop"]), theme.get("slug") or theme.get("theme_slug") or "")


# ── 시청자 배려 멘트(무드 기반 결정적) ────────────────────────────────
_CARE_POOL: dict[str, list[str]] = {
    "chill": ["오늘 하루도 수고 많으셨어요.\n잠시 모든 걸 내려놓고 음악에 기대어 쉬어가세요.\n당신의 하루가 조금 더 편안해지길 바랍니다."],
    "sad": ["마음이 무거운 날도 있죠.\n괜찮아요, 이 음악이 곁에 있을게요.\n천천히, 당신의 속도로 걸어가도 돼요."],
    "energetic": ["새로운 하루, 좋은 에너지로 시작해요.\n이 음악이 당신의 발걸음을 가볍게 해주길.\n오늘도 당신은 충분히 잘하고 있어요."],
    "focus": ["집중이 필요한 지금, 함께할게요.\n잡념은 잠시 내려두고 한 가지에만 몰입해보세요.\n당신의 노력은 분명 빛을 발할 거예요."],
    "happy": ["기분 좋은 하루 되세요!\n좋아하는 음악과 함께라면 평범한 순간도 특별해져요.\n오늘 당신에게 작은 행복이 깃들길."],
}
_CARE_DEFAULT = ["편안한 시간 보내세요.\n좋은 음악이 당신의 하루에 작은 위로가 되길 바랍니다.\n언제나 당신을 응원합니다."]


def _care(theme: dict, vs: dict) -> str:
    mood = str(vs.get("mood_category") or "").lower()
    return _pick(_CARE_POOL.get(mood, _CARE_DEFAULT), theme.get("slug") or "")


# ── 감성 멘트(LLM, 폴백 결정적) ─────────────────────────────────────
_VIBE_SYSTEM = (
    "너는 유튜브 음악 채널의 감성 카피라이터다. "
    "플레이리스트 본문 첫 줄에 들어갈 감성 멘트(3~4줄)를 쓴다. "
    "규칙: 한국어, 줄바꿈으로 구분, 이모지 금지, 따옴표 금지, 해시태그 금지, "
    "장르 영어명 금지, 청자에게 말을 건네는 톤(~해요/~세요), "
    "분위기·장소·시간대를 녹여 감각적으로. 가사 내용이나 곡 제목은 언급하지 마. "
    "멘트 본문만 출력(설명·부연 금지)."
)


def generate_vibe_intro(theme: dict, viz_spec: dict | None) -> str:
    """LLM 감성 멘트(3~4줄). 실패 시 _care() 결정적 풀 폴백."""
    vs = viz_spec or {}
    try:
        from services import music_lyrics
        if _has_tag_combo(theme):
            from services import music_tags
            combo = theme["tag_combo"]
            summary = music_tags.combo_summary_kr(combo)
            style_en = music_tags.tags_to_suno_style(combo)
            user = f"태그 조합: {summary}\n분위기(영어): {style_en}"
        else:
            gen = music_genres.label_kr(music_genres.classify_theme(theme) or "") or theme.get("genre", "")
            mood = str(vs.get("dominant_emotion") or vs.get("mood_category") or theme.get("mood") or "")
            where = str(vs.get("location_en") or "").strip() or "City View"
            situ = str(theme.get("situation") or "")
            user = f"장르: {gen} / 분위기: {mood} / 장소: {where} / 상황: {situ}"
        raw = music_lyrics._call(_VIBE_SYSTEM, user, max_tokens=200)
        lines = [ln.strip() for ln in (raw or "").strip().splitlines() if ln.strip()]
        if lines:
            return "\n".join(lines[:5])
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-meta] 감성 멘트 LLM 실패(폴백): %s", e)
    return _care(theme, vs)


# ── 제목 ──────────────────────────────────────────────────────────────
# LLM 으로 한국어 감성 카피 + 영어 장르·분위기 카피를 한 번에 생성.
# 형식: playlist🎧 {한국어} | {영어} | 광고없음
_TITLE_SYSTEM = (
    "너는 유튜브 음악 플레이리스트 제목 카피라이터다. "
    "한국어 카피와 영어 카피를 | 로 구분해 한 줄로 출력한다. "
    "규칙:\n"
    "1. 출력 형식: 한국어 카피 | 영어 카피  (이것만 출력, 따옴표·설명 금지)\n"
    "2. 한국어 카피: 시청자의 지금 이 순간 상황을 묘사하거나 궁금증·FOMO 유발. "
    "감성적이고 자극적으로. 장르 영어명 금지. 20자 이내.\n"
    "3. 영어 카피: 직역이 아닌 자연스러운 의역. 장르·분위기 키워드 포함(글로벌 SEO). "
    "짧고 강하게. 30자 이내.\n"
    "4. 예:\n"
    "   첫 곡부터 심장 건드림 | cafe vibes that hit different\n"
    "   식어가는 라떼처럼 너도 그렇게 | soft late night cafe pop\n"
    "   틀자마자 기분이 달라지는 | breezy morning drive city pop\n"
    "   도입부부터 미쳤다 진짜 | hiphop beats that go hard"
)

_TITLE_TAG_SYSTEM = (
    "너는 유튜브 음악 플레이리스트 제목 카피라이터다. "
    "한국어 카피와 영어 카피를 | 로 구분해 한 줄로 출력한다. "
    "규칙:\n"
    "1. 출력 형식: 한국어 카피 | 영어 카피  (이것만 출력, 따옴표·설명 금지)\n"
    "2. 유형 지시가 '검색형'이면: 태그 키워드(행동·장르·상황)를 자연스럽게 녹인 검색 친화 문장. "
    "실제 사람들이 유튜브에서 검색할 표현 우선.\n"
    "   유형 지시가 '감성형'이면: 감성 카피를 쓰되 ★검색 키워드를 최소 1개는 반드시 포함"
    "(순수 감성·추상 표현만으로 이루어진 제목 금지).\n"
    "3. 한국어 카피: 장르 영어명 금지. 20자 이내.\n"
    "4. 영어 카피: 태그 영어 키워드 포함(SEO). 30자 이내.\n"
    "5. 행동→검색어 변환: '아기재울때'→'아기 재우는 음악/자장가/수면음악', "
    "'공부할때'→'공부할 때 듣는', '잠들때'→'잠들 때 듣는/수면 음악', "
    "'집중할때'→'집중 음악/집중할 때 듣는'. 사람들이 실제로 검색하는 표현을 쓴다.\n"
    "6. 검색형 예: 공부할때 듣는 로파이 재즈 | lofi jazz for studying\n"
    "   감성형 예: 잠들 때 듣는 피아노 | 비 오는 밤의 위로"
)


def _generate_title_copy(theme: dict, vs: dict) -> tuple[str, str]:
    """LLM 으로 한국어+영어 카피 생성. 실패 시 결정적 폴백."""
    if _has_tag_combo(theme):
        return _generate_title_copy_tag(theme)
    try:
        from services import music_lyrics
        gid = music_genres.classify_theme(theme) or ""
        gen_kr = music_genres.label_kr(gid) or theme.get("genre", "")
        gen_en = _title_genre_en(theme, vs)
        mood = str(vs.get("dominant_emotion") or vs.get("mood_category") or theme.get("mood") or "")
        situ = str(theme.get("situation") or "")
        moods = ", ".join(music_lyrics.MOOD_POOLS.get(gid, []))
        g_style = music_lyrics.GENRE_STYLES.get(gid, "")
        user = (
            f"장르(한국어): {gen_kr}\n장르(영어): {gen_en}\n"
            f"분위기: {mood}\n상황: {situ}\n제목: {theme.get('title_kr', '')}"
        )
        if moods:
            user += f"\n무드 키워드: {moods}"
        if g_style:
            user += f"\n장르 스타일: {g_style}"
        raw = music_lyrics._call(_TITLE_SYSTEM, user, max_tokens=100)
        line = (raw or "").strip().splitlines()[0].strip().strip('"').strip("'").strip()
        if "|" in line:
            parts = [p.strip() for p in line.split("|", 1)]
            if len(parts) == 2 and parts[0] and parts[1]:
                return parts[0][:40], parts[1][:50]
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-meta] 제목 카피 LLM 실패(폴백): %s", e)
    return _copy(theme, vs), _title_genre_en(theme, vs)


def _generate_title_copy_tag(theme: dict) -> tuple[str, str]:
    """태그 조합 기반 제목 카피(검색형 85% / 감성형 15%). 실패 시 결정적 폴백."""
    import random as _rnd
    from services import music_tags
    combo = theme["tag_combo"]
    labels = music_tags.combo_labels_kr(combo)
    summary = music_tags.combo_summary_kr(combo)
    style_en = music_tags.tags_to_suno_style(combo)
    title_type = "검색형" if _rnd.random() < 0.85 else "감성형"
    try:
        from services import music_lyrics
        user = (
            f"유형: {title_type}\n"
            f"태그 한국어: {summary}\n"
            f"태그 영어: {style_en}\n"
            f"행동: {labels.get('action', [''])[0]}\n"
            f"장르: {', '.join(labels.get('genre', []))}\n"
            f"감정: {', '.join(labels.get('emotion', []))}"
        )
        raw = music_lyrics._call(_TITLE_TAG_SYSTEM, user, max_tokens=100)
        line = (raw or "").strip().splitlines()[0].strip().strip('"').strip("'").strip()
        if "|" in line:
            parts = [p.strip() for p in line.split("|", 1)]
            if len(parts) == 2 and parts[0] and parts[1]:
                return parts[0][:40], parts[1][:50]
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-meta] 태그 제목 카피 LLM 실패(폴백): %s", e)
    return summary[:30] or "감성 플레이리스트", style_en[:50] or "mood playlist"


def _title_genre_en(theme: dict, vs: dict) -> str:
    """제목용 장르 영문 — music_genres.label_en(19장르 정확). 미분류 시 genre_en 폴백."""
    gid = music_genres.classify_theme(theme)
    if gid:
        g = music_genres._BY_ID.get(gid)
        if g:
            label = g["label_en"]
            return label if gid in music_genres.PLACE_BGM_IDS else f"{label} Playlist"
    return f"{genre_en(theme, vs).title()} Playlist"


def build_title(theme: dict, viz_spec: dict | None) -> str:
    """playlist🎧 {한국어 감성 카피} | {영어 장르·분위기 카피}. 100자 이내.

    태그 조합이 있으면 곡수(N곡 모음) 포함, '광고없음' 제거.
    태그 없는 기존 경로도 '광고없음' 제거(일관성).
    """
    vs = viz_spec or {}
    ko_copy, en_copy = _generate_title_copy(theme, vs)
    tc = theme.get("track_count") or 0
    tc_label = f" {tc}곡 모음" if isinstance(tc, int) and tc >= 2 else ""
    title = f"playlist🎧 {ko_copy} | {en_copy}{tc_label}".strip()
    if len(title) > 100:
        room = max(4, 100 - len(f"playlist🎧  | {tc_label}"))
        ko_room = room * 2 // 3
        en_room = room - ko_room
        title = f"playlist🎧 {ko_copy[:ko_room]} | {en_copy[:en_room]}{tc_label}"
    return title


# ── 곡별 명언풍 부제(quote) ─────────────────────────────────────────
_QUOTE_SYSTEM = """\
You write short, evocative, aphorism-style English quotes for music video subtitles.
Rules:
- 8-12 words. One sentence. No attribution, no quotation marks.
- NEVER use real famous quotes. Always original/creative.
- Match the emotional core of the provided lyrics or mood.
- Poetic, reflective tone — like a whispered truth, not a slogan.
- No questions. No exclamation marks. No hashtags.
Examples:
- "Some goodbyes echo longer than the love itself"
- "In silence, the heart finally learns to rest"
- "Every lullaby is a quiet act of love"
- "The road home is paved with songs unsung"
"""

_QUOTE_MODEL = "claude-sonnet-4-6"


def generate_track_quotes(tracks: list[dict], theme: dict) -> list[str]:
    """곡별 명언풍 부제 생성(Claude Sonnet 4.6). 실패 시 빈 리스트(폴백=subtitle_en)."""
    if not tracks:
        return []
    try:
        from services import music_lyrics
        if not music_lyrics.is_available():
            return []
    except Exception:  # noqa: BLE001
        return []

    lines: list[str] = []
    for i, t in enumerate(tracks, 1):
        lyrics = (t.get("lyrics") or "").strip()
        if lyrics:
            lines.append(f"Song {i} (vocal — use lyrics emotion):\n{lyrics[:500]}")
        else:
            mood = theme.get("mood") or ""
            action = (theme.get("tag_combo") or {}).get("action") or theme.get("situation") or ""
            genre = theme.get("genre") or ""
            lines.append(f"Song {i} (instrumental — use mood/genre):\naction={action}, mood={mood}, genre={genre}")

    user = f"Generate exactly {len(tracks)} quotes, one per song. Output each quote on its own line (no numbering, no bullets).\n\n" + "\n\n".join(lines)

    try:
        raw = music_lyrics._call(_QUOTE_SYSTEM, user, max_tokens=300, model=_QUOTE_MODEL)
        result = [ln.strip().strip('"').strip("'").strip() for ln in (raw or "").strip().splitlines() if ln.strip()]
        if len(result) >= len(tracks):
            return result[:len(tracks)]
        logger.warning("[music-meta] quote 수 불일치(기대=%d, 생성=%d) — 빈 폴백", len(tracks), len(result))
    except Exception as e:  # noqa: BLE001
        logger.warning("[music-meta] quote 생성 실패(subtitle_en 폴백): %s", e)
    return []



_BASE_TAGS = ["#playlist", "#playlists", "#플리", "#플레이리스트", "#music", "#musician", "#감성", "#감성음악", "#밝은음악"]
_GENRE_TAGS = {
    "city pop": ["#citypop", "#시티팝", "#citypopmusic", "#lofi"],
    "lofi": ["#lofi", "#lofimusic", "#로파이", "#chillmusic"],
    "jazz": ["#jazz", "#cafejazz", "#카페재즈", "#jazzplaylist"],
    "pop": ["#pop", "#popmusic", "#팝송", "#신나는팝송"],
    "acoustic": ["#acoustic", "#acousticmusic", "#어쿠스틱", "#감성어쿠스틱"],
}
_PURPOSE_TAGS = {
    "작업": ["#작업용플리", "#작업용팝", "#workmusic", "#studyplaylist"],
    "카페": ["#카페음악", "#카페플리", "#cafemusic"],
    "수면": ["#수면음악", "#sleepmusic", "#잘때듣는노래"],
    "공부": ["#공부할때듣는음악", "#studymusic"],
    "집중": ["#집중음악", "#focusmusic"],
    "출퇴근": ["#출근길플리", "#출퇴근노래"],
    "출근": ["#출근길플리", "#출퇴근노래"],
    "여행": ["#여행플리", "#여행팝송"],
    "운동": ["#운동음악", "#운동할때듣는노래"],
    "노동요": ["#노동요", "#일할때듣는노래"],
    "휴식": ["#휴식음악", "#힐링음악"],
}
_TIME_TAGS = {
    "night": ["#새벽플리", "#latenight", "#밤에듣는음악"],
    "morning": ["#morningvibes", "#출근길플리"],
    "evening": ["#저녁플리", "#eveningvibes"],
}
_MOOD_TAGS = {
    "chill": ["#chillmusic", "#힐링음악", "#여유"],
    "energetic": ["#신나는노래", "#에너지", "#파워업"],
    "sad": ["#슬픈노래", "#감성발라드"],
    "focus": ["#집중음악", "#공부음악"],
    "happy": ["#밝은음악", "#기분좋아지는음악"],
}
_LOCATION_TAGS: list[tuple[tuple[str, ...], list[str]]] = [
    (("new york", "newyork", "manhattan"), ["#뉴욕플리", "#manhattan"]),
    (("tokyo",), ["#도쿄플리", "#tokyo"]),
    (("paris",), ["#파리플리", "#paris"]),
    (("seoul",), ["#서울플리", "#seoul"]),
    (("london",), ["#런던플리", "#london"]),
]
_FILLER_TAGS = [
    "#youtubemusic", "#musiclover", "#dailymusic", "#무드", "#분위기", "#음악추천",
    "#플레이리스트추천", "#감성플리", "#힐링", "#노래추천", "#bgm", "#배경음악",
]


def _time_bucket(theme: dict, vs: dict) -> str:
    text = " ".join([str(theme.get("situation") or ""), str(vs.get("subtitle_en") or ""), str(vs.get("location_en") or "")]).lower()
    if any(k in text for k in ("새벽", "밤", "night", "dawn", "midnight")):
        return "night"
    if any(k in text for k in ("출근", "morning", "아침", "오전")):
        return "morning"
    if any(k in text for k in ("저녁", "퇴근", "evening", "sunset", "dusk")):
        return "evening"
    return ""


def build_hashtags(theme: dict, viz_spec: dict | None) -> list[str]:
    """해시태그 20~50개 자동 조합(중복 없음).

    태그 조합이 있으면 태그 기반(강세 3개 + 20~30개). 없으면 기존 풀 기반 30~50개.
    """
    if _has_tag_combo(theme):
        return _build_hashtags_tag(theme)
    vs = viz_spec or {}
    tags: list[str] = []
    seen: set[str] = set()

    def add(items: list[str]) -> None:
        for t in items:
            t = re.sub(r"\s+", "", t)
            if not t.startswith("#"):
                t = "#" + t.lstrip("#")
            key = t.lower()
            if len(t) > 1 and key not in seen:
                seen.add(key)
                tags.append(t)

    add(_BASE_TAGS)
    add(_GENRE_TAGS.get(genre_en(theme, vs), _GENRE_TAGS["pop"]))
    for p in _purposes(theme, vs):
        for k, v in _PURPOSE_TAGS.items():
            if k in p:
                add(v)
    tb = _time_bucket(theme, vs)
    if tb:
        add(_TIME_TAGS[tb])
    mc = str(vs.get("mood_category") or "").lower()
    if mc in _MOOD_TAGS:
        add(_MOOD_TAGS[mc])
    loc = str(vs.get("location_en") or "").lower()
    for keys, v in _LOCATION_TAGS:
        if any(k in loc for k in keys):
            add(v)
    # 최소 30개 보장 — 부족하면 필러로 채움. 최대 50개.
    if len(tags) < 30:
        add(_FILLER_TAGS)
    return tags[:50]


def _build_hashtags_tag(theme: dict) -> list[str]:
    """태그 조합 기반 해시태그. 강세 3개(action·genre·emotion) + 나머지 축 + 필러."""
    from services import music_tags
    combo = theme["tag_combo"]
    labels = music_tags.combo_labels_kr(combo)
    tags: list[str] = []
    seen: set[str] = set()

    def add(items: list[str]) -> None:
        for t in items:
            t = re.sub(r"\s+", "", t)
            if not t.startswith("#"):
                t = "#" + t.lstrip("#")
            key = t.lower()
            if len(t) > 1 and key not in seen:
                seen.add(key)
                tags.append(t)

    add(_BASE_TAGS[:4])
    for lbl in labels.get("action", []):
        add([f"#{lbl}", f"#{lbl}듣는음악", f"#{lbl}플리"])
    for lbl in labels.get("genre", []):
        add([f"#{lbl}", f"#{lbl}플레이리스트", f"#{lbl}음악"])
    for lbl in labels.get("emotion", []):
        add([f"#{lbl}", f"#{lbl}음악"])
    for lbl in labels.get("situation", []):
        add([f"#{lbl}", f"#{lbl}음악"])
    for lbl in labels.get("tempo", []):
        add([f"#{lbl}음악"])
    for lbl in labels.get("charm", []):
        add([f"#{lbl}"])
    genre_ids = combo.get("genre") or []
    if isinstance(genre_ids, str):
        genre_ids = [genre_ids]
    for gid in genre_ids:
        en = music_tags.GENRE_TAGS.get(gid, "")
        if en:
            add([f"#{en.replace(' ', '')}"])
    add(_FILLER_TAGS)
    return tags[:35]


# ── 트랙 리스트 ───────────────────────────────────────────────────────
def _hhmmss(sec: float) -> str:
    s = max(0, int(sec))
    h, rem = divmod(s, 3600)
    m, ss = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{ss:02d}"


def build_tracklist(tracks: list[dict]) -> list[str]:
    """[HH:MM:SS] 곡제목 줄 목록. start_sec 없으면 duration 누적으로 계산."""
    lines: list[str] = []
    acc = 0.0
    for i, t in enumerate(tracks or []):
        name = (t.get("title") or "").strip() or f"Track {i + 1}"
        start = t.get("start_sec")
        cur = float(start) if start is not None else acc
        lines.append(f"[{_hhmmss(cur)}] {name}")
        acc = cur + float(t.get("duration") or 0.0)
    return lines


# ── 본문(감성 멘트 + 트랙리스트 + 고정 정보) ─────────────────────────
def build_description(
    theme: dict,
    viz_spec: dict | None,
    tracks: list[dict],
    config: dict | None,
    *,
    hashtags: list[str] | None = None,
    channel_name: str | None = None,
) -> str:
    """본문 3블록: 감성 멘트 → 트랙리스트 → 고정 정보. 빈 소셜·Spotify 는 생략.

    hashtags 를 주면 마지막에 해시태그 섹션 추가(독립 호출/검증용). 다국어 번역 경로는
    본문만 만들고 해시태그를 언어별로 별도 append 한다.
    """
    vs = viz_spec or {}
    cfg = config or {}
    where = str(vs.get("location_en") or "").strip() or "City View"
    flag = _flag(vs)
    emoji = _emoji(theme, vs)
    blocks: list[str] = []

    # [1] 감성 멘트(LLM, 폴백 결정적)
    vibe = generate_vibe_intro(theme, viz_spec)
    blocks.append(vibe)

    # [2] Track list
    tl = build_tracklist(tracks)
    if tl:
        blocks.append("🎵 Track list\n\n" + "\n".join(tl))

    # [3] 고정 정보 블록
    info: list[str] = []
    info.append(f"📍 where;{where} {flag} {emoji}")
    ai = (cfg.get("ai_disclosure") or "").strip()
    if ai:
        info.append(ai)
    spotify = (cfg.get("spotify_url") or "").strip()
    if spotify:
        info.append(f"Spotify 🔗 {spotify}")
    social: list[str] = []
    if (cfg.get("email") or "").strip():
        social.append(f"📧 E-mail: {cfg['email'].strip()}")
    if (cfg.get("instagram") or "").strip():
        social.append(f"📸 Instagram: @{cfg['instagram'].strip().lstrip('@')}")
    if (cfg.get("tiktok") or "").strip():
        social.append(f"🎵 TikTok: @{cfg['tiktok'].strip().lstrip('@')}")
    if social:
        info.extend(social)
    info.append(
        "\n🎵 가장 마음에 드는 노래는 무엇인가요?\n"
        "댓글로 알려주시면 다음 플리에 큰 도움이 됩니다 💚\n\n"
        "🔔 채널 구독하시면 매주 새로운 음악을 받아보실 수 있습니다 🔔"
    )
    info.append(f"Copyright Ⓒ {channel_name or _channel_name()} All rights reserved.")
    blocks.append("\n".join(info))

    # [4] 해시태그(옵션)
    if hashtags:
        blocks.append(" ".join(hashtags))

    sep = f"\n\n{SEP}\n\n"
    return sep.join(blocks).strip()
