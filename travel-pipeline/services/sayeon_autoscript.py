"""사연 트랙 — 자동 사연 생성 (auto-script).

버튼 한 번으로 '도파민 도는' 1인칭 한국어 감성 사연을 자동 작성한다. gpt-4o-mini 1회
(JSON 모드, 동기). 주제 풀에서 랜덤 선택(또는 입력 topic) + 화자 설정(캐릭터 gender/age)
을 반영하고, 매번 다른 주제·반전으로 다양성을 확보한다.

출력 script(여러 줄)는 그대로 대본 칸에 채워지고, 이후 split_script 가 씬으로 쪼갠다.
"""

from __future__ import annotations

import json
import os
import random

from openai import OpenAI

_OPENAI_MODEL = "gpt-4o-mini"

# 랜덤 주제 풀 — 감정 자극 + 공감대가 큰 사연 소재.
_TOPIC_POOL = [
    "가족 — 부모의 말 없는 희생",
    "조부모와의 마지막 추억",
    "철없던 시절의 후회",
    "끝내 말하지 못한 첫사랑·짝사랑",
    "오래된 우정의 소중함",
    "낯선 사람에게 받은 뜻밖의 호의",
    "어른이 되며 겪은 성장통",
    "갑작스러운 이별과 상실",
    "오해로 멀어졌다 화해한 사이",
    "가난했지만 따뜻했던 어린 시절",
    "형제·자매 사이의 미안함과 고마움",
    "선생님/은인에게 못 전한 감사",
]


def _strip_code_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _speaker_hint(character: dict | None) -> str:
    """캐릭터 gender/age 로 화자 힌트 구성(값이 영문이어도 LLM이 처리)."""
    if not character:
        return "20대"
    parts = [str(character.get(k, "")).strip() for k in ("age", "gender")]
    hint = " ".join(p for p in parts if p)
    return hint or "20대"


def _build_system_prompt(speaker: str) -> str:
    return (
        "너는 한국 숏폼 '사연' 채널의 감성 사연 작가다. 시청자의 감정을 강하게 자극하는 "
        "1인칭 한국어 사연을 쓴다.\n\n"
        "[규칙]\n"
        "- 출력은 오직 JSON 객체 하나. 마크다운/설명 금지.\n"
        f"- 화자(1인칭 '나')는 {speaker} 로 설정해 말투·시점을 맞춘다.\n"
        "- 구조: ① 강한 첫 줄 훅(궁금증/충격) → ② 전개 → ③ 반전 또는 깨달음 → "
        "④ 공감을 부르는 마무리 질문.\n"
        "- 길이 6~9줄. 한 줄 = 하나의 나레이션/장면. 각 줄은 자연스러운 구어체 한 문장.\n"
        "- 따뜻하지만 궁금증·감정을 자극하는 톤. 진부한 클리셰·설교 금지.\n"
        "- 실명·특정 브랜드·민감정보 없이. 마지막 줄은 반드시 여운 있는 질문으로 끝낸다.\n\n"
        "[출력 형식]\n"
        '{"script":"첫 줄...\\n둘째 줄...\\n...\\n마지막 질문?","title":"후킹 제목"}\n'
        "script 는 줄바꿈(\\n)으로 구분된 여러 줄 한 문자열. title 은 12자 내외 후킹 제목."
    )


def generate_script(topic: str = "", character: dict | None = None) -> dict:
    """랜덤(또는 지정) 주제로 1인칭 감성 사연을 생성한다.

    Returns: {"script": str(여러 줄), "title": str, "topic": str}
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 미설정 — 사연을 생성할 수 없습니다.")

    chosen = topic.strip() or random.choice(_TOPIC_POOL)
    speaker = _speaker_hint(character)
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=_OPENAI_MODEL,
        messages=[
            {"role": "system", "content": _build_system_prompt(speaker)},
            {
                "role": "user",
                "content": (
                    f"주제: '{chosen}'. 위 규칙대로 매번 다른 설정·전개·반전으로 "
                    "신선한 사연을 JSON 으로 써라."
                ),
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.95,  # 다양성 확보(반복 방지)
    )
    content = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(_strip_code_fence(content))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM 응답 JSON 파싱 실패: {e}") from e

    script = str(data.get("script", "")).strip()
    if not script:
        raise RuntimeError("사연 생성 결과가 비어 있습니다.")
    return {
        "script": script,
        "title": str(data.get("title", "")).strip(),
        "topic": chosen,
    }
