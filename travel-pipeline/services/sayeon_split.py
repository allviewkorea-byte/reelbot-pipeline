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
        else (
            "대본을 자연스러운 호흡/문장 단위로 나눈다 — 한 줄(한 호흡)이 한 씬이다. "
            "대본 길이에 맞춰 씬 수를 정하되 보통 8~16개(짧으면 적게, 길면 많게)."
        )
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
        "- 연출 다양성: 전체 씬에 걸쳐 establishing wide / full-body / medium / "
        "over-the-shoulder / close-up 샷을 고르게 섞는다. 전부 얼굴 클로즈업 금지 — "
        "최소 2~3씬은 인물이 환경 속에 작게 들어간 와이드/풀샷으로 한다. 모든 씬에 "
        "구체적 장소·배경을 넣고 'plain/empty background' 는 절대 쓰지 않는다.\n"
        "- 사연 톤 보존: 1인칭 감성·반전을 유지하고, 마지막 씬은 후킹 질문/여운으로 끝낸다."
        f"{anchor_note}\n\n"
        "[각 씬 필드]\n"
        "- index: 1부터 시작하는 정수.\n"
        "- narration: 국문. TTS가 읽을 자연스러운 한 문장. 대본 표현을 최대한 유지.\n"
        "- subtitle: 국문. 화면 자막. narration을 1~2줄로 압축(가독성), 의미는 유지. "
        "narration보다 짧아야 한다.\n"
        "- highlight: 국문. subtitle 안에 실제로 들어있는 핵심 단어/구 1개(노란 강조용). "
        "반드시 subtitle의 부분 문자열이어야 한다.\n"
        "- image_prompt: 영문. 나레이션 맥락에 맞는 한 장면을 시네마틱하게 묘사한다. "
        "다음을 반드시 포함한다:\n"
        "    · LOCATION/배경: 구체적 장소·환경 (예: rainy back alley, sunset street, "
        "father's study, cafe by the window, bus stop at dusk) + 배경 디테일·깊이감. "
        "'plain/empty background' 절대 금지.\n"
        "    · SHOT TYPE: establishing wide / full-body / medium / over-the-shoulder / "
        "close-up 중 이 씬에 맞는 것(씬마다 다르게, 전체에서 골고루).\n"
        "    · ACTION/동작: 능동적 동작 (예: walking down the alley, unfolding a letter, "
        "looking out the window, turning back to look). 정적 정면 흉상 금지.\n"
        "    · CAMERA: 앵글·심도(shallow/deep depth of field)·구도 변화.\n"
        "    · 표정/감정 + 분위기/조명 (예: tearful eyes; warm morning light, cold blue "
        "night, backlit silhouette, rain on the window).\n"
        "  ⚠️ 인물의 외모·정체성(머리색·머리모양·안경·의상·얼굴 생김새·나이) 은 절대 쓰지 "
        "말 것 — 그건 캐릭터 시트/앵커가 담당한다. 장소·샷·동작·카메라·분위기만 적는다. "
        "인물은 'the character' 로만 지칭. 9:16 세로 구도.\n"
        "- motion: \"zoom_in\" | \"zoom_out\" | \"pan_left\" | \"pan_right\" 중 하나. "
        "연출에 맞게 다양하게(감정 고조=zoom_in, 공간/반전 드러냄=zoom_out, 이동/시선=pan).\n\n"
        "[출력 형식]\n"
        '{"scenes":[{"index":1,"narration":"...","subtitle":"...","highlight":"...",'
        '"image_prompt":"wide establishing shot, the character walking alone down a rainy '
        'back alley at night, neon reflections on wet pavement, seen small within the deep '
        'cluttered background, shallow depth of field, melancholic cold blue mood, '
        'vertical 9:16","motion":"zoom_in"}]}'
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
    count_hint = str(num_scenes) if num_scenes else "8~16"
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
