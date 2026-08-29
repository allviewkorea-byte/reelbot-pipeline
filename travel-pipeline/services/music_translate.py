"""다국어 번역(#32) — 가사·제목·설명을 11개 언어로 번역 + 해시태그 생성.

글로벌 채널 정체성: 공개 업로드 시 자막·메타데이터를 다국어로. Claude(music_lyrics._call)
재사용. ANTHROPIC_API_KEY 없으면 원본 언어만 돌려준다(회귀 안전). **테스트 1곡 생성과 무관**
— 번역은 공개 업로드(검수 UI) 단계에서만 호출된다.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# 번역 대상 10개. 원본(ko)까지 합쳐 ALL_LANGS = 11개. UI 탭 순서와 일치.
TARGET_LANGS = ["en", "ja", "zh", "es", "pt", "ar", "hi", "th", "tl", "vi"]
LANG_NAMES = {
    "ko": "Korean", "en": "English", "ja": "Japanese", "zh": "Chinese (Simplified)",
    "es": "Spanish", "pt": "Portuguese", "ar": "Arabic", "hi": "Hindi",
    "th": "Thai", "tl": "Tagalog (Filipino)", "vi": "Vietnamese",
}
ALL_LANGS = ["ko"] + TARGET_LANGS  # UI: KR EN JA ZH ES PT AR HI TH TL VI

_KOREAN = re.compile(r"[가-힣]")


def detect_source_lang(text: str, default: str = "ko") -> str:
    """가사 원본 언어 감지 — 한글 있으면 ko, 없으면 en(팝송). 텍스트가 비면 default.

    호출부가 `lyrics or title_kr or "ko-"` 처럼 센티넬로 '기본 ko' 를 표현했지만, "ko-"
    에는 한글이 없어 오히려 en 으로 판정됐다. 그 결과 인스트곡(가사 없음) + title_kr 누락
    시 원본 한국어 메타가 en 키로 저장되고 유튜브 defaultLanguage 까지 en 이 됐다.
    빈 입력의 기본값은 센티넬이 아니라 이 인자로 표현한다.
    """
    if not (text or "").strip():
        return default
    return "ko" if _KOREAN.search(text) else "en"


def missing_langs(meta: dict | None) -> list[str]:
    """meta({lang:{title,description}}) 에서 빠졌거나 값이 빈 언어 목록. 완전하면 [].

    캐시 완전성 판정용. 이전 기준은 `len(meta) >= 2` 라서 11개 중 9개가 번역 실패해도
    '완성' 으로 간주돼 누락이 영구 고착됐다. title·description 이 모두 채워진 언어만
    확보된 것으로 본다.
    """
    m = meta if isinstance(meta, dict) else {}
    out: list[str] = []
    for lng in ALL_LANGS:
        d = m.get(lng)
        if not (
            isinstance(d, dict)
            and str(d.get("title") or "").strip()
            and str(d.get("description") or "").strip()
        ):
            out.append(lng)
    return out


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
        raw = music_lyrics._call(system, text, max_tokens=16000)
        data = music_lyrics._extract_json(raw)
        if not isinstance(data, dict):
            return {}
        return {t: str(data[t]) for t in targets if isinstance(data.get(t), str) and data[t].strip()}
    except Exception as e:  # noqa: BLE001 - 번역 실패는 원본 유지(회귀 안전)
        logger.warning("[music-translate] 번역 실패: %s", e)
        return {}


def translate_lyrics(
    lyrics_text: str,
    source_lang: str | None = None,
    *,
    skip_langs: set[str] | None = None,
) -> dict[str, str]:
    """가사 → 원본 + 최대 10개 번역 = 11개 언어(ALL_LANGS). {lang: 가사}.

    #작업지시서 2026-06: 10개 언어를 단일 GPT 콜로 번역하면 출력 JSON 이 길어 뒤쪽 언어
    (일본어 등)가 잘려 누락됐다 → **언어별 1콜**로 분리(generate_localizations 패턴).
    각 콜이 짧아 truncation 원천 제거, 한 언어 실패가 다른 언어에 영향 없음(부분 성공).

    skip_langs: 이미 확보된 언어(캐시 repair 시) — 재번역하지 않는다.
    """
    src = (source_lang or detect_source_lang(lyrics_text)).strip()
    result = {src: lyrics_text}
    if not lyrics_text.strip():
        return result
    skip = skip_langs or set()
    for lng in [t for t in ALL_LANGS if t != src and t not in skip]:
        one = _translate_map(lyrics_text, src, [lng])  # 언어 1개씩 → JSON 잘림 없음
        if one.get(lng, "").strip():
            result[lng] = one[lng]
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
    skip_langs: set[str] | None = None,
    parts: dict | None = None,
) -> dict[str, dict]:
    """제목·설명 11개 언어(ALL_LANGS) → {lang: {title, description}}. GPT 없으면 원본만.

    parts(music_meta.build_description_parts 결과)를 주면 **산문만 번역**한다 —
    제목 + parts["intro"] 만 LLM 을 태우고 트랙리스트·고정정보·Copyright 는 원본을
    그대로 재사용, 고정 안내문은 music_i18n 상수로 채운다. 본문 전체를 번역하던
    기존 방식 대비 출력 토큰이 크게 줄어 모델 출력 상한 압박·JSON 잘림이 사라진다.
    parts 가 없으면 기존 동작 그대로(회귀 안전).

    base_title/base_description 을 주면(#37 music_meta 의 풍부한 제목·본문) 그것을 원본으로
    번역한다. 미지정 시 기존 _base_meta(간단 메타)로 폴백(회귀 안전).

    skip_langs: 이미 확보된 언어(캐시 repair 시) — 재번역하지 않으며 결과에도 담지 않는다
    (호출부가 캐시본을 merge 한다).
    """
    src = detect_source_lang(lyrics or theme.get("title_kr", ""))
    if parts:
        return _localize_from_parts(parts, base_title or "", src, skip_langs=skip_langs)
    if base_title is not None and base_description is not None:
        base_title, base_desc = base_title, base_description
    else:
        base_title, base_desc = _base_meta(theme, viz_spec, lyrics)
    out: dict[str, dict] = {src: {"title": base_title, "description": base_desc}}
    # #37-B: 풍부화 본문(8섹션)은 길어, 10개 언어를 한 번에 번역하면 출력 JSON 이 잘려
    # 파싱 실패 → src 만 남는 버그가 있었다. 언어별 1콜로 분리해 각 콜이 토큰 한도에
    # 충분히 들어가게 하고, 한 언어 실패가 나머지를 막지 않도록 격리한다.
    skip = skip_langs or set()
    targets = [lng for lng in ALL_LANGS if lng != src and lng not in skip]
    for t in targets:
        d = _translate_one_meta(base_title, base_desc, src, t)
        if d:
            out[t] = d
    return out


def _localize_from_parts(
    parts: dict, base_title: str, src: str, *, skip_langs: set[str] | None = None
) -> dict[str, dict]:
    """산문(제목 + 감성멘트)만 번역하고 나머지 조각은 원본으로 재조립.

    언어별 1콜(제목·intro 동시) — 번역 payload 가 감성멘트 몇 줄로 줄어든다.
    트랙리스트는 **어떤 언어에서도 번역하지 않는다**(영상 내 곡 제목과 일치해야 함).
    해시태그는 호출부(_build_localizations)의 언어별 append 경로를 그대로 쓴다.
    """
    from services import music_meta

    intro = parts.get("intro") or ""
    out: dict[str, dict] = {
        src: {"title": base_title, "description": music_meta.assemble_description(parts, src)}
    }
    skip = skip_langs or set()
    for t in [lng for lng in ALL_LANGS if lng != src and lng not in skip]:
        d = _translate_one_meta(base_title, intro, src, t)
        if not d:
            continue  # 언어별 격리 — 실패한 언어만 빠진다(캐시 repair 가 나중에 채움)
        tp = dict(parts)
        tp["intro"] = d.get("description") or intro
        out[t] = {
            "title": d["title"],
            "description": music_meta.assemble_description(tp, t),
        }
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
        # parts 경로에선 payload 가 제목+감성멘트뿐이라 4000 이면 충분하다.
        data = music_lyrics._extract_json(music_lyrics._call(system, user, max_tokens=4000))
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
