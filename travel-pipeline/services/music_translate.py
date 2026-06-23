"""다국어 번역(#32) — 가사·제목·설명을 10개 언어로 번역 + 해시태그 생성.

글로벌 채널 정체성: 공개 업로드 시 자막·메타데이터를 다국어로. Claude(music_lyrics._call)
재사용. ANTHROPIC_API_KEY 없으면 원본 언어만 돌려준다(회귀 안전). **테스트 1곡 생성과 무관**
— 번역은 공개 업로드(검수 UI) 단계에서만 호출된다.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# 지원 언어(원본 제외 9개 + 원본 = 항상 10트랙). UI 탭 순서와 일치.
TARGET_LANGS = ["en", "ja", "zh", "es", "pt", "ar", "hi", "th", "tl", "vi"]
LANG_NAMES = {
    "ko": "Korean", "en": "English", "ja": "Japanese", "zh": "Chinese (Simplified)",
    "es": "Spanish", "pt": "Portuguese", "ar": "Arabic", "hi": "Hindi",
    "th": "Thai", "tl": "Tagalog (Filipino)", "vi": "Vietnamese",
}
ALL_LANGS = ["ko"] + TARGET_LANGS  # UI: KR EN JA ZH ES PT AR HI TH TL VI

_KOREAN = re.compile(r"[가-힣]")


def detect_source_lang(text: str) -> str:
    """가사 원본 언어 감지 — 한글 있으면 ko, 아니면 en(팝송 기본)."""
    return "ko" if _KOREAN.search(text or "") else "en"


def _is_available() -> bool:
    from services import music_lyrics
    return music_lyrics.is_available()


def _translate_map(text: str, source: str, targets: list[str]) -> dict[str, str]:
    """text 를 targets 각 언어로 번역 → {lang: 번역}. 한 번의 GPT 호출(JSON). 실패 시 {}."""
    if not text.strip() or not targets:
        return {}
    try:
        from services import music_lyrics
        names = ", ".join(f"{t}={LANG_NAMES.get(t, t)}" for t in targets)
        system = (
            "You are a professional song/lyrics translator. Translate the given text from "
            f"{LANG_NAMES.get(source, source)} into these languages: {names}. "
            "Keep line breaks and the singable, natural tone (not literal). "
            'Return STRICT JSON only: {"<lang>": "<translation>", ...}. No markdown.'
        )
        raw = music_lyrics._call(system, text, max_tokens=3000)
        data = music_lyrics._extract_json(raw)
        if not isinstance(data, dict):
            return {}
        return {t: str(data[t]) for t in targets if isinstance(data.get(t), str) and data[t].strip()}
    except Exception as e:  # noqa: BLE001 - 번역 실패는 원본 유지(회귀 안전)
        logger.warning("[music-translate] 번역 실패: %s", e)
        return {}


def translate_lyrics(lyrics_text: str, source_lang: str | None = None) -> dict[str, str]:
    """가사 → 원본 + 9개 번역 = 10개 언어. {lang: 가사}."""
    src = (source_lang or detect_source_lang(lyrics_text)).strip()
    result = {src: lyrics_text}
    if not _is_available():
        return result
    targets = [lng for lng in ALL_LANGS if lng != src]
    result.update(_translate_map(lyrics_text, src, targets))
    return result


def _base_meta(theme: dict, viz_spec: dict | None, lyrics: str) -> tuple[str, str]:
    """원본(한국어) 제목·설명 초안 — WHERE/Genre/Vibe 메타 + 가사 발췌 포함."""
    vs = viz_spec or {}
    title_kr = (theme.get("title_kr") or theme.get("title") or "").strip()
    genre = (theme.get("genre") or "").strip()
    title = f"{title_kr} | {genre} Playlist".strip(" |") if genre else title_kr
    where = str(vs.get("location_en") or "").strip()
    vibe = str(vs.get("dominant_emotion") or vs.get("mood_category") or "").strip()
    lines = [title_kr]
    meta = [b for b in (f"WHERE : {where}" if where else "", f"Genre : {genre}" if genre else "",
                        f"Vibe : {vibe}" if vibe else "") if b]
    if meta:
        lines += ["", *meta]
    if lyrics.strip():
        lines += ["", "— Lyrics —", lyrics.strip()[:600]]
    return title[:100], "\n".join(lines).strip()


def generate_localizations(
    theme: dict,
    viz_spec: dict | None,
    lyrics: str = "",
    *,
    base_title: str | None = None,
    base_description: str | None = None,
) -> dict[str, dict]:
    """제목·설명 10개 언어 → {lang: {title, description}}. GPT 없으면 원본만.

    base_title/base_description 을 주면(#37 music_meta 의 풍부한 제목·본문) 그것을 원본으로
    번역한다. 미지정 시 기존 _base_meta(간단 메타)로 폴백(회귀 안전).
    """
    src = detect_source_lang(lyrics or theme.get("title_kr", "") or "ko-")
    if base_title is not None and base_description is not None:
        base_title, base_desc = base_title, base_description
    else:
        base_title, base_desc = _base_meta(theme, viz_spec, lyrics)
    out: dict[str, dict] = {src: {"title": base_title, "description": base_desc}}
    if not _is_available():
        return out
    # #37-B: 풍부화 본문(8섹션)은 길어, 10개 언어를 한 번에 번역하면 출력 JSON 이 잘려
    # 파싱 실패 → src 만 남는 버그가 있었다. 언어별 1콜로 분리해 각 콜이 토큰 한도에
    # 충분히 들어가게 하고, 한 언어 실패가 나머지를 막지 않도록 격리한다.
    targets = [lng for lng in ALL_LANGS if lng != src]
    for t in targets:
        d = _translate_one_meta(base_title, base_desc, src, t)
        if d:
            out[t] = d
    return out


def _translate_one_meta(base_title: str, base_desc: str, src: str, target: str) -> dict | None:
    """제목·설명을 target 언어 1개로 번역(1콜). 실패 시 None(원본 유지). 𝐏𝐥𝐚𝐲𝐥𝐢𝐬𝐭·이모지·
    영문 장르 토큰은 그대로 보존(번역 금지)하도록 지시한다."""
    try:
        from services import music_lyrics
        tname = LANG_NAMES.get(target, target)
        system = (
            f"Translate this YouTube music video TITLE and DESCRIPTION from "
            f"{LANG_NAMES.get(src, src)} into {tname}. Natural and YouTube-friendly. "
            "Keep the special bold word 𝐏𝐥𝐚𝐲𝐥𝐢𝐬𝐭, all emojis, URLs, @handles, hashtags, "
            "and English genre tokens (city pop, lofi, jazz, pop, acoustic) UNCHANGED. "
            "Title <=100 chars. "
            'Return STRICT JSON only: {"title": "...", "description": "..."}. No markdown.'
        )
        user = f"TITLE:\n{base_title}\n\nDESCRIPTION:\n{base_desc}"
        data = music_lyrics._extract_json(music_lyrics._call(system, user, max_tokens=3000))
        if isinstance(data, dict) and data.get("title") and data.get("description"):
            return {"title": str(data["title"])[:100], "description": str(data["description"])}
    except Exception as e:  # noqa: BLE001 - 언어별 격리
        logger.warning("[music-translate] %s 번역 실패: %s", target, e)
    return None


def generate_hashtags(theme: dict, viz_spec: dict | None) -> list[str]:
    """해시태그 — 영어 5~7 + 한국어 3~5 + 무드/장소 2~3 (총 10~15). 결정적(비용 0)."""
    vs = viz_spec or {}
    genre = (theme.get("genre") or "").strip().replace(" ", "")
    mood = (theme.get("mood") or "").strip()
    where = str(vs.get("location_en") or "").strip()
    mood_cat = str(vs.get("mood_category") or "").strip()
    tags: list[str] = []

    def add(t: str) -> None:
        t = re.sub(r"\s+", "", t).strip("#")
        if t and f"#{t}" not in tags:
            tags.append(f"#{t}")

    for t in ("playlist", "music", "lofi", "chill", "studymusic", "relaxingmusic", "citypop"):
        add(t)
    for t in ("플레이리스트", "음악", "감성음악", "공부할때듣는음악"):
        add(t)
    for t in (genre, mood_cat, mood, where.replace(" ", "")):
        if t:
            add(t)
    return tags[:15]
