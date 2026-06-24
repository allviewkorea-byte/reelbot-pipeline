"""가사 자동생성 (Rooftop Music) — Claude API 3-스테이지.

①다양성 플랜(1콜): 주제 → N개 서로 다른 sub_theme / 핵심 메시지 / 화자 / 상황 / 감정 배정
②작성(곡당 1콜): 플랜 + 가사 헌법 → 깊이있는 가사(섹션 태그 + 영어 훅)
③자기검토(곡당 1콜): 깊이/여운/단조/클리셰 채점 → 어느 항목이든 7 미만이면 재작성

가사 품질의 유일한 기준점은 prompts/lyrics_guidelines.md(가사 헌법)이며, 매 호출
로드해 프롬프트에 박는다. 모델은 기본 claude-opus-4-8(품질 우선), env MUSIC_LYRICS_MODEL
로 교체(검수 시 sonnet-4-6 비교용). anthropic SDK(>=0.40.0, 기존 의존성) 사용.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# 가사 헌법 경로(이 파일 기준 ../prompts/).
_GUIDELINES_PATH = Path(__file__).resolve().parent.parent / "prompts" / "lyrics_guidelines.md"

# 기본 모델 — 품질 우선(채널의 영혼). env 한 줄로 교체 가능.
_DEFAULT_MODEL = "claude-opus-4-8"

# 자기검토 통과 바(원칙 6): 4기준 모두 이 점수 이상이어야 채택.
_REVIEW_BAR = 7

# 기본 sub-주제 풀(다양성 가이드, 시티팝). 플랜이 참고하되 그대로 베끼지 않는다.
DEFAULT_SUBTHEME_POOL = [
    "한밤 드라이브", "여름 바다", "금요일 밤", "첫눈에", "옥상 파티", "네온사인",
    "늦은 밤 전화", "주말 아침", "카세트테이프", "비 갠 도시", "너와 춤을", "별빛 고속도로",
]


def _model() -> str:
    return (os.getenv("MUSIC_LYRICS_MODEL") or _DEFAULT_MODEL).strip()


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
) -> list[dict]:
    """주제 → N개의 서로 다른 곡 설계(sub_theme/core_message/화자/상황/감정/title/style)."""
    pool = sub_theme_pool or DEFAULT_SUBTHEME_POOL
    guidelines = load_guidelines()
    system = (
        "너는 시티팝 장르에 정통한 한국어 작사 디렉터다. 아래 '가사 헌법'을 절대 기준으로 "
        "삼아, 서로 확실히 구별되는 곡들을 기획한다. 클리셰·범용 기획을 금지한다.\n\n"
        f"=== 가사 헌법 ===\n{guidelines}"
    )
    user = (
        f"주제: {theme}\n곡 수: {n}\n언어: {language} (시티팝이면 한국어 기반 + 영어 훅 살짝)\n"
        f"참고 sub-주제 풀(그대로 베끼지 말고 변형/확장): {', '.join(pool)}\n\n"
        f"원칙 5(다양성)에 따라 {n}곡이 서로 다른 sub-주제·화자·상황·감정이 되도록 기획하라. "
        "각 곡마다 원칙 1의 '핵심 메시지'(주제 라벨이 아니라 듣는 사람에게 전하고 싶은 말 한 줄)를 정하라.\n\n"
        "JSON 배열로만 응답. 각 원소:\n"
        "{\"sub_theme\":\"...\",\"core_message\":\"한 줄\",\"speaker\":\"화자 설정\","
        "\"situation\":\"상황/장면\",\"emotion\":\"감정의 결\",\"title\":\"곡 제목\","
        "\"style\":\"시티팝 변주 스타일(영문, sunoapi style 용)\",\"vocalGender\":\"male|female\"}"
    )
    data = _extract_json(_call(system, user, max_tokens=2200, model=model))
    if not isinstance(data, list):
        raise RuntimeError("플랜 응답이 배열이 아닙니다.")
    return data[:n]


# ── 스테이지 2: 작성 ─────────────────────────────────────────────────────
def write_lyrics(plan: dict, *, language: str = "ko", model: str | None = None, tone: str | None = None) -> str:
    """플랜 1개 → 깊이있는 가사(섹션 태그). 가사 텍스트만 반환.

    tone(선택): 주제의 lyric_tone 한 줄. 있으면 작성 컨텍스트에 추가(없으면 현행과 동일).
    """
    guidelines = load_guidelines()
    system = (
        "너는 시티팝 작사가다. 아래 '가사 헌법'의 모든 원칙을 지켜 한 곡을 쓴다. "
        "telling 금지, 장면으로 showing. 클리셰 한 줄도 금지.\n\n"
        f"=== 가사 헌법 ===\n{guidelines}"
    )
    tone_line = f"- 이 곡의 톤: {tone}\n" if (tone or "").strip() else ""
    user = (
        "다음 설계로 가사를 써라.\n"
        f"- sub_theme: {plan.get('sub_theme')}\n"
        f"- 핵심 메시지(모든 구절이 이걸 향함): {plan.get('core_message')}\n"
        f"- 화자: {plan.get('speaker')}\n"
        f"- 상황/장면: {plan.get('situation')}\n"
        f"- 감정의 결: {plan.get('emotion')}\n"
        f"- 제목: {plan.get('title')}\n"
        f"{tone_line}"
        f"- 언어: {language} (한국어 기반 + 영어 훅 살짝)\n\n"
        "원칙 7 형식: [Verse]/[Pre-Chorus]/[Chorus]/[Bridge]/[Outro] 섹션 태그 포함. "
        "원칙 3: 끝에 잔상/전환을 남겨라.\n"
        "가사 본문만 출력(설명·해설 금지)."
    )
    return _call(system, user, max_tokens=1600, model=model).strip()


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
    data = _extract_json(_call(system, user, max_tokens=2000, model=model))
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
    progress=None,
) -> list[dict]:
    """주제 → N곡 가사(헌법 기반 3-스테이지). 곡별 dict 리스트 반환.

    tone(선택): 주제의 lyric_tone. 작성 단계에 전달(없으면 현행과 완전 동일).
    반환 원소: {sub_theme, core_message, title, lyrics, style, vocalGender?, scores, revised, issues}
    """
    if not is_available():
        raise RuntimeError("ANTHROPIC_API_KEY 미설정 — 가사 생성 불가")

    if progress:
        progress(f"① 다양성 플랜 생성({n}곡)...")
    plans = plan_songs(
        theme, n, sub_theme_pool=sub_theme_pool, language=language, model=model
    )

    songs: list[dict] = []
    for i, plan in enumerate(plans, 1):
        try:
            if progress:
                progress(f"② 작성 {i}/{len(plans)}: {plan.get('sub_theme')}")
            draft = write_lyrics(plan, language=language, model=model, tone=tone)
            if progress:
                progress(f"③ 자기검토 {i}/{len(plans)}...")
            review = review_lyrics(plan, draft, language=language, model=model)
            songs.append({
                "sub_theme": plan.get("sub_theme", ""),
                "core_message": plan.get("core_message", ""),
                "title": plan.get("title", ""),  # #52-A 빈값 허용 → 다운스트림이 Suno 자동 제목 사용(장르명+번호 방지)
                "style": plan.get("style", "") or theme,
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
