"""사연 트랙 — 씬 분할 (PR-S1).

국문 사연 대본 → 씬 리스트(JSON). 각 씬은 S2(이미지)/S3(TTS)/S4(합성)에 필요한
필드를 모두 담는다. gpt-4o-mini 1회 호출(JSON 모드, 동기).

출력 scenes 의 image_prompt[] 는 그대로 PR-S2 generate_scenes 입력 형식이 된다
(자동 오케스트레이션 연결은 후속; S1 은 잘 형성된 scenes 만 반환).
"""

from __future__ import annotations

import json
import os

from openai import OpenAI

_OPENAI_MODEL = "gpt-4o-mini"
_ALLOWED_MOTIONS = ("zoom_in", "zoom_out", "pan_left", "pan_right")


def _strip_code_fence(raw: str) -> str:
    """혹시 모델이 코드펜스로 감싸면 제거(JSON 모드라 보통 불필요한 방어선)."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _build_system_prompt(num_scenes: int | None, character_anchor: str) -> str:
    count_rule = (
        f"대본을 정확히 {num_scenes}개 씬으로 나눈다."
        if num_scenes
        else "대본을 자연스러운 감정 비트 단위로 6~10개 씬으로 나눈다."
    )
    anchor_note = ""
    if character_anchor and character_anchor.strip():
        anchor_note = (
            "\n- 화자(인물)의 외모는 별도 시스템이 시트로 처리한다. "
            "참고용 캐릭터 앵커: "
            f"'{character_anchor.strip()}' — 이 정보를 image_prompt 에 외모 묘사로 옮기지 말 것."
        )
    return (
        "당신은 한국 '사연' 숏폼 영상의 씬 분할 전문가다. "
        "입력으로 1인칭 감성 사연 대본(국문)을 받아 영상 제작용 씬 리스트를 만든다.\n\n"
        "[규칙]\n"
        "- 출력은 오직 JSON 객체 하나. 마크다운/코드펜스/설명/주석 절대 금지.\n"
        f"- {count_rule}\n"
        "- 씬 1개 = 나레이션 1줄 = 자막 1개 (1:1 대응).\n"
        "- 대본에 충실히 쪼갠다. 내용을 새로 지어내지 않는다(재창작 금지).\n"
        "- 사연 톤 보존: 1인칭 감성·반전을 유지하고, 마지막 씬은 후킹 질문/여운으로 끝낸다."
        f"{anchor_note}\n\n"
        "[각 씬 필드]\n"
        "- index: 1부터 시작하는 정수.\n"
        "- narration: 국문. TTS가 읽을 자연스러운 한 문장. 대본 표현을 최대한 유지.\n"
        "- subtitle: 국문. 화면 자막. narration을 1~2줄로 압축(가독성), 의미는 유지. "
        "narration보다 짧아야 한다.\n"
        "- highlight: 국문. subtitle 안에 실제로 들어있는 핵심 단어/구 1개(노란 강조용). "
        "반드시 subtitle의 부분 문자열이어야 한다.\n"
        "- image_prompt: 영문. 배경·상황·동작·감정·구도만 묘사한다. "
        "⚠️ 인물의 외모(머리색·머리모양·안경·의상·얼굴 생김새·나이) 절대 쓰지 말 것. "
        "인물은 'the character' 정도로만 지칭. 9:16 세로 구도, 인물 중앙 배치를 고려.\n"
        "- motion: \"zoom_in\" | \"zoom_out\" | \"pan_left\" | \"pan_right\" 중 하나. "
        "연출에 맞게 다양하게(감정 고조=zoom_in, 공간/반전 드러냄=zoom_out, 이동/시선=pan).\n\n"
        "[출력 형식]\n"
        '{"scenes":[{"index":1,"narration":"...","subtitle":"...","highlight":"...",'
        '"image_prompt":"...","motion":"zoom_in"}]}'
    )


def _normalize_scenes(raw_scenes: list) -> list[dict]:
    """LLM 출력 정규화: 1부터 재인덱싱, motion enum 보정, 문자열 strip,
    highlight 가 subtitle 부분문자열이 아니면 비운다."""
    out: list[dict] = []
    for i, s in enumerate(raw_scenes, 1):
        if not isinstance(s, dict):
            continue
        motion = str(s.get("motion", "")).strip().lower()
        if motion not in _ALLOWED_MOTIONS:
            motion = "zoom_in"
        subtitle = str(s.get("subtitle", "")).strip()
        highlight = str(s.get("highlight", "")).strip()
        if highlight and highlight not in subtitle:
            highlight = ""
        out.append({
            "index": i,
            "narration": str(s.get("narration", "")).strip(),
            "subtitle": subtitle,
            "highlight": highlight,
            "image_prompt": str(s.get("image_prompt", "")).strip(),
            "motion": motion,
        })
    return out


def split_script(
    script: str,
    num_scenes: int | None = None,
    character_anchor: str = "",
) -> dict:
    """국문 사연 대본을 씬 리스트로 분할한다.

    Returns: {"scenes": [{index, narration, subtitle, highlight, image_prompt, motion}, ...]}
    """
    if not script or not script.strip():
        raise ValueError("script(사연 대본)가 비어 있습니다.")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 미설정 — 씬 분할을 할 수 없습니다.")

    client = OpenAI(api_key=api_key)
    system = _build_system_prompt(num_scenes, character_anchor)
    count_hint = str(num_scenes) if num_scenes else "6~10"
    user = (
        f"[사연 대본]\n{script.strip()}\n\n"
        f"위 대본을 {count_hint}개 씬으로 분할해 JSON으로 출력하라."
    )

    resp = client.chat.completions.create(
        model=_OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.4,
    )
    content = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(_strip_code_fence(content))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM 응답 JSON 파싱 실패: {e}") from e

    scenes = _normalize_scenes(data.get("scenes", []) if isinstance(data, dict) else [])
    if not scenes:
        raise RuntimeError("씬 분할 결과가 비어 있습니다 (LLM 출력 형식 확인 필요).")
    return {"scenes": scenes}
