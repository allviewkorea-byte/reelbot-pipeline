"""Claude 장애 시 OpenAI 대체(1회) — 음악 파이프라인 LLM 이중화(2026-10-19 대표 승인).

사고: Anthropic 잔액 소진(400)으로 가사·검수·제목이 이틀간 전부 실패했다. Claude 호출이 실패하면
같은 작업을 OpenAI 로 한 번만 대신 돌린다. 평소(Claude 정상)에는 호출 0회 = 비용 0.

범위(승인 1): music_lyrics._call(가사·제목·프롬프트 변주·번역·주제 등 공통 경로) + 이미지 검수.
         렌더 로고 검사(music_recovery)는 실패해도 렌더를 막지 않아 대상에서 뺀다.
조건(승인 2): Anthropic API 오류 전부 — 잔액 부족 400·401/402·429·5xx·529·타임아웃·연결.
         JSON 파싱 실패 등 응답 내용 문제는 대체하지 않는다(기존 처리 그대로).
모델(승인 3): 가사 작성·검토 = gpt-4o, 비전 검수 = gpt-4o, 나머지 = gpt-4o-mini. env 로 덮는다.
         JSON 모드(response_format)는 쓰지 않는다 — 가사 플랜이 배열을 요구해 객체 전용 모드와
         맞지 않는다. 글자로 받아 기존 _extract_json·_parse_review 가 그대로 읽는다.
끄기: MUSIC_LLM_FALLBACK=off (기본 openai).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_TIMEOUT_SEC = 120.0


class FallbackFailed(RuntimeError):
    """Claude 도 OpenAI 대체도 실패 — 실패 사유 코드 llm_unavailable 판정에 쓴다."""


def is_llm_unavailable(e: BaseException | None) -> bool:
    """예외 사슬(__cause__·__context__) 어디에든 LLM 불가(대체 실패·Claude API 오류·키 없음)가 있나."""
    seen = 0
    while e is not None and seen < 8:
        if isinstance(e, FallbackFailed) or is_anthropic_api_error(e) or "ANTHROPIC_API_KEY 미설정" in str(e):
            return True
        e = e.__cause__ or e.__context__
        seen += 1
    return False


def enabled() -> bool:
    mode = (os.getenv("MUSIC_LLM_FALLBACK") or "openai").strip().lower()
    return mode == "openai" and bool((os.getenv("OPENAI_API_KEY") or "").strip())


def text_model(strong: bool = False) -> str:
    if strong:
        return (os.getenv("MUSIC_LLM_FALLBACK_LYRICS_MODEL") or "gpt-4o").strip()
    return (os.getenv("MUSIC_LLM_FALLBACK_MODEL") or "gpt-4o-mini").strip()


def vision_model() -> str:
    return (os.getenv("MUSIC_LLM_FALLBACK_VISION_MODEL") or "gpt-4o").strip()


def is_anthropic_api_error(e: BaseException) -> bool:
    """대체 대상 = Anthropic SDK 의 API 오류(상태코드 오류·타임아웃·연결 오류 모두 APIError 하위)."""
    try:
        import anthropic
    except ImportError:  # pragma: no cover - SDK 없으면 대체 판단 불가
        return False
    return isinstance(e, anthropic.APIError)


def reason_of(e: BaseException) -> str:
    status = getattr(e, "status_code", None)
    name = type(e).__name__
    return f"{name}{f'({status})' if status else ''}: {str(e)[:120]}"


def _client():
    from openai import OpenAI
    return OpenAI(api_key=(os.getenv("OPENAI_API_KEY") or "").strip(), timeout=_TIMEOUT_SEC, max_retries=1)


def _text_of(resp) -> str:
    choices = getattr(resp, "choices", None) or []
    if not choices:
        raise RuntimeError("OpenAI 응답이 비어 있습니다.")
    return (choices[0].message.content or "").strip()


def text(system: str, user: str, *, max_tokens: int, strong: bool = False, task: str = "", cause: BaseException) -> str:
    """system+user → OpenAI 텍스트 1회. 실패하면 원래 Claude 오류와 함께 예외."""
    model = text_model(strong)
    logger.warning("[llm-fallback] task=%s claude 실패 → openai %s 대체 (사유: %s)", task or "-", model, reason_of(cause))
    try:
        resp = _client().chat.completions.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return _text_of(resp)
    except Exception as e:  # noqa: BLE001
        raise FallbackFailed(f"LLM 대체도 실패(task={task}): claude={reason_of(cause)} / openai={str(e)[:160]}") from e


def vision(system: str, image_b64_jpeg: str, prompt: str, *, max_tokens: int, task: str = "", cause: BaseException) -> tuple[str, str]:
    """이미지(base64 JPEG)+지시 → OpenAI 비전 1회. (텍스트, 모델) 반환."""
    model = vision_model()
    logger.warning("[llm-fallback] task=%s claude 실패 → openai %s 대체 (사유: %s)", task or "-", model, reason_of(cause))
    try:
        resp = _client().chat.completions.create(
            model=model, max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64_jpeg}"}},
                    {"type": "text", "text": prompt},
                ]},
            ],
        )
        return _text_of(resp), model
    except Exception as e:  # noqa: BLE001
        raise FallbackFailed(f"LLM 대체도 실패(task={task}): claude={reason_of(cause)} / openai={str(e)[:160]}") from e
