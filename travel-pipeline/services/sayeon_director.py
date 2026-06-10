"""사연 트랙 — 디렉터 단계 (샷 설계).

대본 분할 후, gpt-4o-mini 가 각 씬 비트의 샷 스펙(shot_type / camera_angle / action /
setting / mood)을 구조화 출력한다. 이미지 프롬프트를 이 스펙으로 구성해 '우연한 흉상
나열'이 아닌 '의도된 연출'을 만든다.

- 캐릭터 정체성(외모)은 시트/앵커가 담당하므로 여기서는 외모를 적지 않는다(인물='the character').
- 실패/JSON 깨짐 시 기존 image_prompt 로 폴백한다(파이프라인 안 멈춤).
- 모델/엔드포인트/씬 수(대본 길이 기반)는 건드리지 않는다 — image_prompt 내용만 구성.
"""

from __future__ import annotations

import json
import logging
import os

from openai import OpenAI

logger = logging.getLogger(__name__)

_OPENAI_MODEL = "gpt-4o-mini"
_SHOT_TYPES = ("wide", "full", "medium", "over_the_shoulder", "close_up")

# shot_type → 영문 샷 묘사구(이미지 프롬프트 앞부분).
_SHOT_PHRASE = {
    "wide": "wide establishing shot, the character small within the environment",
    "full": "full-body shot",
    "medium": "medium shot",
    "over_the_shoulder": "over-the-shoulder shot",
    "close_up": "close-up shot",
}


def _strip_code_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _build_director_prompt(n: int) -> str:
    return (
        "너는 한국 숏폼 '사연' 영상의 연출 디렉터다. 분할된 씬 비트마다 샷 스펙을 설계한다.\n\n"
        "[규칙]\n"
        f'- 출력은 오직 JSON 객체 하나: {{"shots":[...]}}. shots 길이는 정확히 {n}개(비트와 1:1).\n'
        '- 각 shot 필드: shot_type("wide"|"full"|"medium"|"over_the_shoulder"|"close_up"), '
        "camera_angle(영문), action(영문, 인물의 능동 동작), setting(영문, 구체적 장소·환경), "
        "mood(영문, 분위기/조명).\n"
        "- 첫 씬(index 1) = wide (establishing, 장소·상황 제시).\n"
        "- 감정 피크/반전 비트 = close_up.\n"
        "- 연속한 두 씬의 shot_type 을 같게 하지 않는다(다양성).\n"
        "- 같은 장소는 연속 씬에서 setting 을 일관 유지(연속성). 장면이 바뀔 때만 setting 변경.\n"
        "- 대화/대면 비트 = over_the_shoulder.\n"
        "- 전체에서 최소 2~3씬은 wide 또는 full(인물이 환경 속에 작게).\n"
        "- setting 은 대본 맥락에서 일관되게 추론. 스토리 아크를 따라 클로즈업 비중을 점차 높인다.\n"
        "- ⚠️ 인물 외모·정체성(머리·안경·의상·얼굴·나이)은 절대 쓰지 않는다 — 캐릭터 시트가 "
        "담당한다. 인물은 'the character' 로만 지칭.\n\n"
        "[출력 예시]\n"
        '{"shots":[{"shot_type":"wide","camera_angle":"low angle","action":"walking alone",'
        '"setting":"a rainy back alley at night with neon reflections",'
        '"mood":"melancholic cold blue"}]}'
    )


def _normalize_shots(shots: list, n: int) -> list[dict]:
    """길이 n 보장 + shot_type enum 보정 + 첫 씬 wide 보장 + 연속 중복 완화."""
    out: list[dict] = []
    for i in range(n):
        s = shots[i] if i < len(shots) and isinstance(shots[i], dict) else {}
        st = str(s.get("shot_type", "")).strip().lower().replace("-", "_").replace(" ", "_")
        if st not in _SHOT_TYPES:
            st = "wide" if i == 0 else "medium"
        out.append({
            "shot_type": st,
            "camera_angle": str(s.get("camera_angle", "")).strip(),
            "action": str(s.get("action", "")).strip(),
            "setting": str(s.get("setting", "")).strip(),
            "mood": str(s.get("mood", "")).strip(),
        })
    # 첫 씬은 establishing wide 보장
    out[0]["shot_type"] = "wide"
    # 연속 동일 shot_type 완화(다양성)
    for i in range(1, n):
        if out[i]["shot_type"] == out[i - 1]["shot_type"]:
            out[i]["shot_type"] = "close_up" if out[i]["shot_type"] != "close_up" else "medium"
    return out


def design_shots(script: str, scenes: list[dict]) -> list[dict]:
    """대본 + 씬 비트 → 씬별 샷 스펙(비트와 동일 길이). 실패 시 예외."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 미설정 — 디렉터를 실행할 수 없습니다.")
    n = len(scenes)
    beats = [
        {"index": s.get("index", i + 1), "narration": str(s.get("narration", "")).strip()}
        for i, s in enumerate(scenes)
    ]
    client = OpenAI(api_key=api_key)
    user = (
        f"[전체 대본]\n{script.strip()}\n\n"
        f"[씬 비트 {n}개]\n{json.dumps(beats, ensure_ascii=False)}\n\n"
        f"각 비트에 1:1 대응하는 shots 배열({n}개)을 JSON으로 출력하라."
    )
    resp = client.chat.completions.create(
        model=_OPENAI_MODEL,
        messages=[
            {"role": "system", "content": _build_director_prompt(n)},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.5,
    )
    content = resp.choices[0].message.content or "{}"
    data = json.loads(_strip_code_fence(content))
    shots = data.get("shots") if isinstance(data, dict) else None
    if not isinstance(shots, list) or not shots:
        raise RuntimeError("디렉터 출력에 shots 배열이 없습니다.")
    return _normalize_shots(shots, n)


def compose_image_prompt(spec: dict, fallback: str = "") -> str:
    """샷 스펙 → 영문 이미지 프롬프트(장면 내용만; 외모/정체성·STYLE 은 build_scene_prompt 담당)."""
    st = str(spec.get("shot_type", "medium"))
    parts = [_SHOT_PHRASE.get(st, "medium shot")]
    if spec.get("camera_angle"):
        parts.append(str(spec["camera_angle"]))
    if spec.get("action"):
        parts.append(f"the character {spec['action']}")
    if spec.get("setting"):
        parts.append(f"at {spec['setting']}")
    if spec.get("mood"):
        parts.append(str(spec["mood"]))
    parts.append("vertical 9:16")
    composed = ", ".join(p for p in parts if p)
    return composed or fallback


def apply_director(script: str, scenes: list[dict]) -> list[dict]:
    """씬 리스트의 image_prompt 를 디렉터 샷 스펙으로 구성해 돌려준다.

    실패하면 입력 scenes 를 그대로 반환(기존 image_prompt 폴백 — 파이프라인 안 멈춤).
    """
    if not scenes:
        return scenes
    try:
        shots = design_shots(script, scenes)
    except Exception as e:  # noqa: BLE001
        logger.warning("디렉터 단계 실패 — 기존 image_prompt 로 폴백: %s", e)
        return scenes

    out: list[dict] = []
    for i, s in enumerate(scenes):
        spec = shots[i] if i < len(shots) else {}
        composed = compose_image_prompt(spec, fallback=str(s.get("image_prompt", "")))
        ns = dict(s)
        if composed:
            ns["image_prompt"] = composed
        out.append(ns)
    return out
