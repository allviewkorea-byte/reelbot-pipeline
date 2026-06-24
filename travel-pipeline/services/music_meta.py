"""YouTube 메타데이터 풍부화(#37) — 제목·본문·해시태그 자동 생성(결정적, 비용 0).

글로벌 음악 채널 SEO·시청자 경험: 𝐏𝐥𝐚𝐲𝐥𝐢𝐬𝐭 시그니처 제목, 8섹션 본문(위치·환영·
AI 명시·플랫폼·소셜·트랙리스트·참여유도·저작권), 30~50개 해시태그. 모두 결정적
조합(GPT 미사용) — 테스트 1곡/제작 비용 무변경. 다국어 번역은 music_translate 가
이 결과를 입력으로 받아 처리(공개 업로드 단계에서만).

빈 슬로건·소셜은 해당 줄/섹션을 출력하지 않는다(조건부 분기). viz_spec 이 없거나
키가 비어도 안전 기본으로 동작한다.
"""

from __future__ import annotations

import logging
import os
import re

from services import music_genres  # #52-E 장르 영문 라벨(label_en) — 19장르 정확 표기

logger = logging.getLogger(__name__)

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


# ── 제목 ──────────────────────────────────────────────────────────────
# #52-E 자극적 후킹 카피 — LLM 으로 매번 다른 클릭 유도 카피 생성. 실패 시 기존 풀 폴백.
_HOOK_SYSTEM = (
    "너는 유튜브 음악 플레이리스트 썸네일용 한국어 후킹 카피라이터다. "
    "도파민·중독·미쳤다·취하다·한계돌파·홀린다 같은 강한 클릭 유도 표현을 쓴다. "
    "장르 분위기에 맞춰라(힙합=강렬, 발라드·R&B=감성, BGM=편안/고급). "
    "규칙: 한국어 한 줄, 18자 이내, 따옴표·이모지·해시태그·장르 영어명 없이 카피 문구만 출력. "
    "예: 이 리듬감에 중독됩니다 / 도입부부터 미쳤다 진짜 / 새벽 감성에 취하는 밤 / 카페에서 틀어놓기만 하세요"
)


def _hook_copy(theme: dict, vs: dict) -> str:
    """LLM 후킹 카피 1개(매번 다름). 실패/미설정 시 _COPY_POOL(결정적) 폴백."""
    try:
        from services import music_lyrics
        if music_lyrics.is_available():
            gen = music_genres.label_kr(music_genres.classify_theme(theme) or "") or theme.get("genre", "")
            mood = str(vs.get("dominant_emotion") or vs.get("mood_category") or theme.get("mood") or "")
            user = f"장르: {gen} / 분위기: {mood} / 제목: {theme.get('title_kr', '')}"
            raw = music_lyrics._call(_HOOK_SYSTEM, user, max_tokens=80)
            copy = (raw or "").strip().splitlines()[0].strip().strip('"').strip("'").strip()
            if copy and len(copy) <= 30 and "|" not in copy:
                return copy
    except Exception as e:  # noqa: BLE001 - 카피 생성 실패는 폴백
        logger.debug("[music-meta] 후킹 카피 LLM 실패(폴백): %s", e)
    return _copy(theme, vs)


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
    """#52-E playlist🎧 {자극적 카피} | {장르 영문} | 광고없음. 100자 이내. '광고없음' 항상 끝."""
    vs = viz_spec or {}
    copy = _hook_copy(theme, vs)
    gen = _title_genre_en(theme, vs)
    title = f"playlist🎧 {copy} | {gen} | 광고없음".strip()
    if len(title) > 100:
        # '광고없음' 보존 — 카피를 줄여 100자 보장.
        keep = f"playlist🎧  | {gen} | 광고없음"
        room = max(4, 100 - len(keep))
        title = f"playlist🎧 {copy[:room]} | {gen} | 광고없음"
    return title


# ── 해시태그 ──────────────────────────────────────────────────────────
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
    """해시태그 30~50개 자동 조합(중복 없음). 베이스+장르+용도+시간대+무드+위치(+필러)."""
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


# ── 본문(8섹션) ───────────────────────────────────────────────────────
def build_description(
    theme: dict,
    viz_spec: dict | None,
    tracks: list[dict],
    config: dict | None,
    *,
    hashtags: list[str] | None = None,
    channel_name: str | None = None,
) -> str:
    """8개 섹션 본문. 빈 슬로건·소셜·Spotify 는 해당 줄/섹션 생략(조건부 분기).

    hashtags 를 주면 [8] 해시태그 섹션까지 포함(독립 호출/검증용). 다국어 번역 경로는
    본문(1~7)만 만들고 해시태그를 언어별로 별도 append 한다.
    """
    vs = viz_spec or {}
    cfg = config or {}
    where = str(vs.get("location_en") or "").strip() or "City View"
    flag = _flag(vs)
    emoji = _emoji(theme, vs)
    blocks: list[str] = []

    # [1] 위치 + 환영 멘트
    s1 = [f"📍 {where} {flag} {emoji}", "", _care(theme, vs), "", "오늘도 좋은 음악과 함께하세요 🎧"]
    slogan_en = (cfg.get("slogan_en") or "").strip()
    if slogan_en:
        s1 += ["", slogan_en]
    blocks.append("\n".join(s1))

    # [2] AI 명시
    ai = (cfg.get("ai_disclosure") or "").strip()
    if ai:
        blocks.append(ai)

    # [3] 외부 플랫폼 — Spotify URL 있을 때만
    spotify = (cfg.get("spotify_url") or "").strip()
    if spotify:
        blocks.append(
            "📀 Apple Music · Spotify · YouTube Music · iTunes 에서 감상하실 수 있습니다\n"
            f"Spotify 🔗 {spotify}"
        )

    # [4] 소셜 — 입력된 것만
    social: list[str] = []
    if (cfg.get("email") or "").strip():
        social.append(f"📧 E-mail: {cfg['email'].strip()}")
    if (cfg.get("instagram") or "").strip():
        social.append(f"📸 Instagram: @{cfg['instagram'].strip().lstrip('@')}")
    if (cfg.get("tiktok") or "").strip():
        social.append(f"🎵 TikTok: @{cfg['tiktok'].strip().lstrip('@')}")
    if social:
        blocks.append("\n".join(social))

    # [5] Track list — 자동 생성
    tl = build_tracklist(tracks)
    if tl:
        blocks.append("🎵 Track list\n\n" + "\n".join(tl))

    # [6] 참여 유도 — 고정
    blocks.append(
        "🎵 가장 마음에 드는 노래는 무엇인가요?\n"
        "댓글로 알려주시면 다음 플리에 큰 도움이 됩니다 💚\n\n"
        "🔔 채널 구독하시면 매주 새로운 음악을 받아보실 수 있습니다 🔔"
    )

    # [7] 저작권
    blocks.append(f"Copyright Ⓒ {channel_name or _channel_name()} All rights reserved.")

    # [8] 해시태그(옵션)
    if hashtags:
        blocks.append(" ".join(hashtags))

    sep = f"\n\n{SEP}\n\n"
    return sep.join(blocks).strip()
