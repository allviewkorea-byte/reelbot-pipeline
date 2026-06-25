"""가사 자동생성 (Rooftop Music) — Claude API 3-스테이지.

①다양성 플랜(1콜): 주제 → N개 서로 다른 sub_theme / 핵심 메시지 / 화자 / 상황 / 감정 배정
②작성(곡당 1콜): 플랜 + 가사 헌법 → 깊이있는 가사(섹션 태그 + 영어 훅)
③자기검토(곡당 1콜): 깊이/여운/단조/클리셰 채점 → 어느 항목이든 7 미만이면 재작성

가사 품질의 유일한 기준점은 prompts/lyrics_guidelines.md(가사 헌법)이며, 매 호출
로드해 프롬프트에 박는다. 모델은 공통 CLAUDE_MODEL(기본 Haiku, 비용 절감), env
MUSIC_LYRICS_MODEL 로 개별 교체 가능. anthropic SDK(>=0.40.0, 기존 의존성) 사용.
"""

from __future__ import annotations

import json
import logging
import os
import random
from pathlib import Path

from config import CLAUDE_MODEL

logger = logging.getLogger(__name__)

# 가사 헌법 경로(이 파일 기준 ../prompts/).
_GUIDELINES_PATH = Path(__file__).resolve().parent.parent / "prompts" / "lyrics_guidelines.md"

# 기본 모델 — 공통 CLAUDE_MODEL(비용 절감 Haiku). MUSIC_LYRICS_MODEL env 로 개별 오버라이드.
_DEFAULT_MODEL = CLAUDE_MODEL

# 자기검토 통과 바(원칙 6): 4기준 모두 이 점수 이상이어야 채택.
_REVIEW_BAR = 7

# 곡 길이 목표(3분 50초~4분 20초)를 위한 가사 구조 — 섹션별 라인 수 명시.
# Suno 는 가사 분량에 비례해 곡을 늘리므로, 충분한 섹션·라인을 채워야 2분대를 벗어난다.
_SONG_STRUCTURE = (
    "[Intro]\n"
    "[Verse 1] (8줄)\n"
    "[Pre-Chorus] (4줄)\n"
    "[Chorus] (6줄)\n"
    "[Verse 2] (8줄)\n"
    "[Pre-Chorus] (4줄)\n"
    "[Chorus] (6줄)\n"
    "[Bridge] (4줄)\n"
    "[Chorus] (6줄)\n"
    "[Outro] (2줄)"
)

# Suno 스타일 길이 힌트 — 위 구조와 함께 곡을 3분 50초~4분 20초로 늘리도록.
_LENGTH_STYLE_HINT = "extended, long song"

# 기본 sub-주제 풀(다양성 가이드, 시티팝). 플랜이 참고하되 그대로 베끼지 않는다.
DEFAULT_SUBTHEME_POOL = [
    "한밤 드라이브", "여름 바다", "금요일 밤", "첫눈에", "옥상 파티", "네온사인",
    "늦은 밤 전화", "주말 아침", "카세트테이프", "비 갠 도시", "너와 춤을", "별빛 고속도로",
]

# ── 19장르 분위기 풀 — 장르마다 어울리는 정서. 영상 1개당 랜덤 2~3개를 뽑아 N곡 공통 톤으로. ──
MOOD_POOLS: dict[str, list[str]] = {
    "citypop":        ["도시적", "아련한", "설레는", "쓸쓸한", "몽환적", "차가운", "새벽감성"],
    "sunset_drive":   ["해방감", "신나는", "탁트인", "아련한", "드라이브감성", "석양같은", "자유로운"],
    "morning_drive":  ["시원한", "신나는", "설레는", "활기찬", "상쾌한", "두근거리는", "기대되는"],
    "cafe":           ["포근한", "사색적", "잔잔한", "아늑한", "혼자인", "고요한", "흐릿한"],
    "jazz":           ["취한듯한", "몽환적", "도시적", "세련된", "깊은밤", "차가운", "관능적"],
    "ballad":         ["애틋한", "먹먹한", "그리운", "아련한", "눈물나는", "따뜻한", "가슴시린"],
    "breakup":        ["쓸쓸한", "아련한", "눈물나는", "차가운", "텅빈", "먹먹한", "돌아서는"],
    "workout":        ["폭발적", "신나는", "짜릿한", "강렬한", "한계돌파", "불타는", "역동적", "비트강렬한"],
    "sleep_study":    ["고요한", "몽환적", "포근한", "흐릿한", "잔잔한", "평화로운", "집중하는"],
    "lofi":           ["아늑한", "흐릿한", "사색적", "비오는날", "혼자인", "잔잔한", "몽글몽글한"],
    "kpop":           ["중독적", "신나는", "두근거리는", "짜릿한", "폭발적", "설레는", "화려한", "비트강렬한"],
    "pop":            ["신나는", "달달한", "해방감", "활기찬", "풋풋한", "여름같은", "밝은"],
    "rnb_soul":       ["취한듯한", "달달한", "묵직한", "깊은", "관능적", "몽환적", "그루브한"],
    "hiphop":         ["냉소적", "강렬한", "반항적", "날카로운", "자신감넘치는", "폭발직전", "거친", "비트강렬한"],
    "hotel_lobby":    ["고요한", "도시적", "포근한", "세련된", "우아한", "잔잔한"],
    "cafe_bgm":       ["잔잔한", "아늑한", "포근한", "흐릿한", "배경같은", "따뜻한"],
    "bar_lounge":     ["취한듯한", "몽환적", "도시적", "깊은밤", "세련된", "관능적"],
    "spa_meditation": ["고요한", "평화로운", "신비로운", "비워지는", "잔잔한", "치유하는"],
    "library_study":  ["사색적", "고요한", "아늑한", "집중하는", "깊은", "차분한"],
}

# ── 장르 음악 스타일(악기·BPM·사운드만 — 소재 단어 없음). 가사 작성의 '음악 결' 참고용. ──
GENRE_STYLES: dict[str, str] = {
    "citypop":        "레트로 신디사이저, 펑키 베이스, 80년대 도시 사운드",
    "sunset_drive":   "일렉 기타, 드라이브 비트, 석양 감성 사운드",
    "morning_drive":  "업템포 비트, 경쾌한 기타, 밝은 사운드",
    "cafe":           "어쿠스틱 기타, 중간 BPM, 따뜻한 톤",
    "jazz":           "재즈 피아노, 색소폰, 스윙 리듬",
    "ballad":         "피아노, 현악기, 느린 BPM",
    "breakup":        "피아노, 어쿠스틱 기타, 감성적 사운드",
    "workout":        "강렬한 비트, 베이스 드롭, 빠른 BPM",
    "sleep_study":    "앰비언트, 소프트 피아노, 느린 BPM",
    "lofi":           "로파이 비트, 빈티지 샘플, 중간 BPM",
    "kpop":           "댄스 비트, 신디사이저, 중고속 BPM",
    "pop":            "팝 비트, 기타, 밝고 경쾌한 사운드",
    "rnb_soul":       "R&B 그루브, 소울 보컬, 중간 BPM",
    "hiphop":         "강렬한 808 베이스, 트랩 비트, 빠른 플로우",
    "hotel_lobby":    "피아노 솔로, 앰비언트, 느린 BPM",
    "cafe_bgm":       "어쿠스틱, 보사노바, 중간 BPM",
    "bar_lounge":     "재즈 피아노, 색소폰, 칵테일 감성",
    "spa_meditation": "앰비언트 신디사이저, 자연음, 매우 느린 BPM",
    "library_study":  "클래식 피아노, 첼로, 조용한 사운드",
}


def pick_moods(genre_id: str | None, n: int = 2) -> list[str]:
    """장르 풀에서 랜덤 2~3개 분위기 선택. 풀 없으면 빈 리스트.

    ⚠️ 영상 1개(N곡)당 1회만 호출해 N곡에 같은 결과를 공유한다(일관성). n 은 호환용(미사용).
    """
    pool = MOOD_POOLS.get((genre_id or "").strip(), [])
    if not pool:
        return []
    count = random.randint(2, 3)  # 매번 2개 또는 3개
    return random.sample(pool, min(count, len(pool)))


def _model() -> str:
    return (os.getenv("MUSIC_LYRICS_MODEL") or _DEFAULT_MODEL).strip()


def _with_length_hint(style: str) -> str:
    """Suno style 문자열에 길이 힌트(extended, long song)를 붙인다(중복 회피)."""
    base = (style or "").strip()
    low = base.lower()
    if "extended" in low and "long song" in low:
        return base
    return f"{base}, {_LENGTH_STYLE_HINT}".strip(", ").strip() if base else _LENGTH_STYLE_HINT


def is_available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _client():
    try:
        import anthropic
    except ImportError as e:  # noqa: BLE001
        raise RuntimeError("anthropic 미설치 — pip install anthropic>=0.40.0") from e
    key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY 미설정")
    return anthropic.Anthropic(api_key=key)


def load_guidelines() -> str:
    """가사 헌법 로드. 없으면 빈 문자열(생성은 진행하되 경고)."""
    try:
        return _GUIDELINES_PATH.read_text(encoding="utf-8")
    except OSError:
        logger.warning("가사 헌법 파일 없음: %s", _GUIDELINES_PATH)
        return ""


def _strip_code_fence(text: str) -> str:
    """```json ... ``` 코드펜스를 제거(narration.py 패턴)."""
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1] if "```" in raw[3:] else raw[3:]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _extract_json(text: str):
    """모델 응답에서 JSON(객체/배열)을 관대하게 추출해 파싱."""
    raw = _strip_code_fence(text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 첫 [ 또는 { 부터 마지막 ] 또는 } 까지 슬라이스 재시도.
    for open_c, close_c in (("[", "]"), ("{", "}")):
        i, j = raw.find(open_c), raw.rfind(close_c)
        if i != -1 and j != -1 and j > i:
            try:
                return json.loads(raw[i : j + 1])
            except json.JSONDecodeError:
                continue
    raise RuntimeError(f"가사 응답 JSON 파싱 실패: {raw[:300]}")


def _call(system: str, user: str, *, max_tokens: int = 2000, model: str | None = None) -> str:
    """Claude messages.create 1회 호출 → 텍스트 반환."""
    client = _client()
    msg = client.messages.create(
        model=model or _model(),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text


# ── 스테이지 1: 다양성 플랜 ───────────────────────────────────────────────
def plan_songs(
    theme: str,
    n: int,
    *,
    sub_theme_pool: list[str] | None = None,
    language: str = "ko",
    model: str | None = None,
    moods: list[str] | None = None,
) -> list[dict]:
    """주제 → N개의 서로 다른 곡 설계(sub_theme/core_message/화자/상황/감정/title/style).

    moods(선택): 영상 1개(N곡) 공통 분위기 조합. 주면 그 정서로 일관되게 기획하고,
    장르 자체를 소재로 한 표현(카페→커피 등)은 금지한다.
    """
    pool = sub_theme_pool or DEFAULT_SUBTHEME_POOL
    guidelines = load_guidelines()
    system = (
        "너는 한국어 작사 디렉터다. 아래 '가사 헌법'을 절대 기준으로 삼아, 서로 확실히 "
        "구별되는 곡들을 기획한다. 클리셰·범용 기획을 금지한다.\n\n"
        f"=== 가사 헌법 ===\n{guidelines}"
    )
    title_rule = (
        "각 곡의 title(곡 제목)은 반드시 한글로 작성하라(영어 제목 금지). "
        "영어 훅 단어는 가사 본문에만 살짝 쓰고, 제목 자체는 한국어여야 한다.\n"
        if str(language).lower().startswith("ko")
        else ""
    )
    moods_str = ", ".join(moods) if moods else ""
    mood_line = (
        f"분위기(이 영상 {n}곡 공통, 일관 유지): {moods_str}\n" if moods_str else ""
    )
    user = (
        f"{mood_line}곡 수: {n}\n언어: {language} (한국어 기반 + 영어 훅 살짝)\n"
        f"참고 sub-주제 풀(그대로 베끼지 말고 변형/확장): {', '.join(pool)}\n\n"
        f"원칙 5(다양성)에 따라 {n}곡이 서로 다른 sub-주제·화자·상황·감정이 되도록 기획하라"
        + (f"(단, 위 분위기 정서는 {n}곡 모두 일관 유지). " if moods_str else ". ")
        + "각 곡마다 원칙 1의 '핵심 메시지'(주제 라벨이 아니라 듣는 사람에게 전하고 싶은 말 한 줄)를 정하라.\n"
        "⚠️ 장르 연상 소재 금지: 장르 이름이나 그 장르를 떠올리게 하는 소재(예: 카페→커피·라떼, "
        "재즈→색소폰)를 가사 소재로 쓰지 말 것. 소재는 분위기에 맞게 자유롭게 고른다.\n"
        f"{title_rule}\n"
        "JSON 배열로만 응답. 각 원소:\n"
        "{\"sub_theme\":\"...\",\"core_message\":\"한 줄\",\"speaker\":\"화자 설정\","
        "\"situation\":\"상황/장면\",\"emotion\":\"감정의 결\",\"title\":\"곡 제목\","
        "\"style\":\"음악 변주 스타일(영문, sunoapi style 용)\",\"vocalGender\":\"male|female\"}"
    )
    data = _extract_json(_call(system, user, max_tokens=4400, model=model))
    if not isinstance(data, list):
        raise RuntimeError("플랜 응답이 배열이 아닙니다.")
    return data[:n]


# ── 스테이지 2: 작성 ─────────────────────────────────────────────────────
def write_lyrics(
    plan: dict,
    *,
    language: str = "ko",
    model: str | None = None,
    tone: str | None = None,
    moods: list[str] | None = None,
    genre_style: str | None = None,
) -> str:
    """플랜 1개 → 깊이있는 가사(섹션 태그). 가사 텍스트만 반환.

    tone(선택): 주제의 lyric_tone 한 줄. moods(선택): 영상 공통 분위기 조합(전체 톤).
    genre_style(선택): 장르의 음악 스타일(악기·BPM·사운드만, 소재 아님).
    """
    guidelines = load_guidelines()
    system = (
        "너는 한국어 작사가다. 아래 '가사 헌법'의 모든 원칙을 지켜 한 곡을 쓴다. "
        "telling 금지, 장면으로 showing. 클리셰 한 줄도 금지.\n\n"
        f"=== 가사 헌법 ===\n{guidelines}"
    )
    tone_line = f"- 이 곡의 톤: {tone}\n" if (tone or "").strip() else ""
    moods_str = ", ".join(moods) if moods else ""
    mood_line = f"- 분위기(가사 전체 톤으로 일관 유지): {moods_str}\n" if moods_str else ""
    style_line = (
        f"- 장르 음악 스타일(악기·BPM·사운드만, 소재 아님): {genre_style}\n"
        if (genre_style or "").strip() else ""
    )
    hook_rule = (
        f"3. 분위기({moods_str})를 가사 전체 톤으로 일관되게 유지.\n" if moods_str else ""
    )
    user = (
        "다음 설계로 가사를 써라.\n"
        f"- sub_theme: {plan.get('sub_theme')}\n"
        f"- 핵심 메시지(모든 구절이 이걸 향함): {plan.get('core_message')}\n"
        f"- 화자: {plan.get('speaker')}\n"
        f"- 상황/장면: {plan.get('situation')}\n"
        f"- 감정의 결: {plan.get('emotion')}\n"
        f"- 제목: {plan.get('title')}\n"
        f"{mood_line}{style_line}{tone_line}"
        f"- 언어: {language} (한국어 기반 + 영어 훅 살짝)\n\n"
        "규칙:\n"
        "1. 첫 소절 첫 라인부터 강렬하거나 인상적인 훅으로 시작 — 진부한 도입부 금지"
        "('그날을 기억해', '눈을 감으면' 등). 듣는 사람이 첫 줄에 바로 빠져들게.\n"
        "2. 가사 소재는 장르와 무관하게 자유롭게 — 카페 장르라도 커피·라떼 같은 장르 연상 소재 금지. "
        "분위기에 맞는 소재를 자유롭게 선택.\n"
        f"{hook_rule}"
        "원칙 7 형식: 아래 구조를 그대로 따라 섹션 태그와 각 섹션의 지정 라인 수를 채워라"
        "(곡 길이 3분 50초~4분 20초 목표 — 분량 부족 금지). 후렴(Chorus)은 반복하되 "
        "매번 똑같이 베끼지 말고 미세한 변주를 줘라.\n"
        f"{_SONG_STRUCTURE}\n"
        "원칙 3: 끝에 잔상/전환을 남겨라.\n"
        "가사 본문만 출력(설명·해설 금지)."
    )
    return _call(system, user, max_tokens=2400, model=model).strip()


# ── 스테이지 3: 자기검토 ─────────────────────────────────────────────────
def review_lyrics(
    plan: dict, lyrics: str, *, language: str = "ko", model: str | None = None
) -> dict:
    """깊이/여운/단조/클리셰 채점 → 미달이면 재작성. {scores, passed, lyrics} 반환."""
    guidelines = load_guidelines()
    system = (
        "너는 깐깐한 작사 심사위원 겸 리라이터다. '가사 헌법' 원칙 6에 따라 냉정히 채점하고, "
        "어느 항목이든 7 미만이면 직접 더 좋게 다시 쓴다. 자기합리화 금지.\n\n"
        f"=== 가사 헌법 ===\n{guidelines}"
    )
    user = (
        f"핵심 메시지: {plan.get('core_message')}\n언어: {language}\n\n"
        f"=== 검토할 가사 ===\n{lyrics}\n\n"
        "원칙 6의 4기준(깊이/여운/단조로움/클리셰)을 0~10으로 채점하라. "
        "(단조로움·클리셰는 '문제 없음=높은 점수') 어느 항목이든 7 미만이면 가사를 "
        "헌법에 맞게 더 깊고 구체적으로 다시 써라. 모두 7 이상이면 원문 유지.\n\n"
        "JSON으로만 응답:\n"
        "{\"scores\":{\"depth\":int,\"resonance\":int,\"monotony\":int,\"cliche\":int},"
        "\"revised\":true|false,\"issues\":\"미달 사유(있으면)\",\"lyrics\":\"최종 가사(섹션 태그 포함)\"}"
    )
    data = _extract_json(_call(system, user, max_tokens=3000, model=model))
    scores = data.get("scores") or {}
    passed = all(int(scores.get(k, 0)) >= _REVIEW_BAR for k in ("depth", "resonance", "monotony", "cliche")) if scores else False
    final_lyrics = (data.get("lyrics") or lyrics).strip()
    return {
        "scores": scores,
        "passed": passed,
        "revised": bool(data.get("revised")),
        "issues": data.get("issues") or "",
        "lyrics": final_lyrics,
    }


# ── 오케스트레이션: 3-스테이지 ────────────────────────────────────────────
def generate_lyrics(
    theme: str,
    n: int,
    *,
    sub_theme_pool: list[str] | None = None,
    language: str = "ko",
    model: str | None = None,
    tone: str | None = None,
    genre_id: str | None = None,
    progress=None,
) -> list[dict]:
    """주제 → N곡 가사(헌법 기반 3-스테이지). 곡별 dict 리스트 반환.

    tone(선택): 주제의 lyric_tone. 작성 단계에 전달(없으면 현행과 완전 동일).
    genre_id(선택): 19장르 id. 있으면 분위기 조합을 **1회만** 뽑아 N곡 전체에 공유(일관성) +
    장르 음악 스타일(소재 아님)을 작성에 전달. 장르 소재(카페→커피 등)는 프롬프트에서 금지.
    반환 원소: {sub_theme, core_message, title, lyrics, style, vocalGender?, scores, revised, issues}
    """
    if not is_available():
        raise RuntimeError("ANTHROPIC_API_KEY 미설정 — 가사 생성 불가")

    # ── N곡 일관성: 분위기 조합을 영상 1개당 1회만 선택 → 모든 곡에 같은 조합 전달. ──
    moods = pick_moods(genre_id)
    genre_style = GENRE_STYLES.get((genre_id or "").strip(), "")
    if progress and moods:
        progress(f"분위기 조합({', '.join(moods)}) — {n}곡 공통")

    if progress:
        progress(f"① 다양성 플랜 생성({n}곡)...")
    plans = plan_songs(
        theme, n, sub_theme_pool=sub_theme_pool, language=language, model=model, moods=moods,
    )

    songs: list[dict] = []
    for i, plan in enumerate(plans, 1):
        try:
            if progress:
                progress(f"② 작성 {i}/{len(plans)}: {plan.get('sub_theme')}")
            draft = write_lyrics(
                plan, language=language, model=model, tone=tone,
                moods=moods, genre_style=genre_style,
            )
            if progress:
                progress(f"③ 자기검토 {i}/{len(plans)}...")
            review = review_lyrics(plan, draft, language=language, model=model)
            songs.append({
                "sub_theme": plan.get("sub_theme", ""),
                "core_message": plan.get("core_message", ""),
                "title": plan.get("title", ""),  # #52-A 빈값 허용 → 다운스트림이 Suno 자동 제목 사용(장르명+번호 방지)
                # Suno 스타일에 길이 힌트 추가(extended, long song) → 곡을 3분 50초~4분 20초로.
                "style": _with_length_hint(plan.get("style", "") or theme),
                "vocalGender": plan.get("vocalGender") or None,
                "lyrics": review["lyrics"],
                "scores": review["scores"],
                "revised": review["revised"],
                "issues": review["issues"],
            })
        except Exception as e:  # noqa: BLE001 - 곡 1개 실패가 전체를 막지 않게
            logger.warning("[lyrics] 곡 %d 생성 실패: %s", i, e)
    if not songs:
        raise RuntimeError("가사 생성 결과가 비어 있습니다(전 곡 실패).")
    return songs
