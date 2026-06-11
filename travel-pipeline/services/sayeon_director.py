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

# 피사체 유형(이 컷에서 '무엇을' 보여줄지). 캐릭터 레퍼런스는 protagonist/two_shot 에만
# 강하게 적용하고, detail/mood/flashback 은 사물·배경 컷이라 캐릭터를 넣지 않는다.
_SUBJECT_TYPES = ("protagonist", "two_shot", "detail", "mood", "flashback")
_PROTAGONIST_CAP = 0.4  # protagonist 단독 샷 비중 상한(인물 포트레이트 반복 방지)

# subject_type → 프레이밍 문구(이미지 프롬프트 구성용).
_SUBJECT_PHRASE = {
    "protagonist": "the protagonist character in frame",
    "two_shot": "two-shot, the protagonist together with the other character",
    "detail": "object detail close-up as an emotional symbol, no character in frame",
    "mood": "atmospheric background-only scene, empty of characters, mood and place",
    "flashback": "flashback scene, faded desaturated colors, a different time and place",
}

# 컷 감정(흰곰 표정 매핑의 재료 — 표정 문구 변환은 PR③ 프롬프트 빌더에서).
_EMOTIONS = ("joy", "sadness", "shock", "anger", "flutter", "anxiety", "deadpan")

# two_shot 에서 상대 캐릭터의 역할(캐스팅 팔레트 키, sayeon_character.CASTING_PALETTE).
# 디렉터가 등장인물을 식별하면 후속 빌더가 역할→동물 매핑을 주입한다(주인공 외 곰 금지).
_SUPPORT_ROLES = ("male_lead", "female_lead", "friend", "family", "villain")


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
        'subject_type("protagonist"|"two_shot"|"detail"|"mood"|"flashback"), '
        'emotion("joy"|"sadness"|"shock"|"anger"|"flutter"|"anxiety"|"deadpan"), '
        'other_role(two_shot 일 때 상대 역할 "male_lead"|"female_lead"|"friend"|"family"'
        '|"villain", 아니면 ""), '
        "include_protagonist(detail/mood 일 때만 의미 — 그 컷에 주인공 곰을 작게/일부만 "
        "담는 게 문장을 더 잘 보여주면 true, 순수 사물·배경이 나으면 false), "
        "camera_angle(영문), action(영문, 능동 동작), setting(영문, 구체적 장소·환경), "
        "mood(영문, 분위기/조명).\n"
        "- subject_type 의미: protagonist=주인공 단독 / two_shot=상대와 2인 / "
        "detail=감정을 상징하는 사물 클로즈업(예: 식어가는 커피, 읽씹된 메신저 화면) / "
        "mood=인물 없는 배경·무드(빈 방, 밤거리) / flashback=회상(낮은 채도, 다른 시공간).\n"
        "- two_shot 이면 상대의 역할(other_role)을 반드시 지정한다(남자=male_lead, "
        "여자=female_lead, 친구=friend, 가족·어른=family, 얄미운 역=villain). 외모는 쓰지 말 것.\n"
        "- detail/mood 의 include_protagonist 는 강제 규칙이 아니다 — '그 문장을 가장 잘 "
        "보여주는 그림'이 기준. 곰 발이 컵을 감싸는 클로즈업처럼 곰 일부가 나으면 true, "
        "읽씹된 채팅 화면 단독처럼 사물만이 나으면 false.\n"
        f"- protagonist 단독 샷은 전체의 {int(_PROTAGONIST_CAP * 100)}% 이하로 제한한다 — "
        "사물(detail)·배경(mood)·회상(flashback)을 적극 섞어 인물 반복을 피한다.\n"
        "- 감정 피크/반전 비트 = detail 클로즈업을 우선 고려(상징 사물로 감정 표현), "
        "차선으로 close_up.\n"
        f"- 마지막 씬(index {n}) 고정: subject_type=protagonist, 정면(카메라 응시), "
        "시청자에게 질문을 던지는 분위기(질문 엔딩 시그니처 컷).\n"
        "- 첫 씬(index 1) = wide (establishing, 장소·상황 제시).\n"
        "- 연속한 두 씬의 shot_type 을 같게 하지 않는다(다양성).\n"
        "- 같은 장소는 연속 씬에서 setting 을 일관 유지(연속성). 장면이 바뀔 때만 setting 변경.\n"
        "- 대화/대면 비트 = two_shot + over_the_shoulder.\n"
        "- 전체에서 최소 2~3씬은 wide 또는 full(인물이 환경 속에 작게).\n"
        "- setting 은 대본 맥락에서 일관되게 추론. 스토리 아크를 따라 샷 강도를 점차 높인다.\n"
        "- ⚠️ 인물 외모·정체성(털색·체형·의상·얼굴)은 절대 쓰지 않는다 — 캐릭터 시트가 "
        "담당한다. 인물은 'the character' 로만 지칭.\n\n"
        "[출력 예시]\n"
        '{"shots":[{"shot_type":"wide","subject_type":"mood","emotion":"anxiety",'
        '"other_role":"","include_protagonist":false,'
        '"camera_angle":"low angle","action":"empty street scene",'
        '"setting":"a rainy back alley at night with neon reflections",'
        '"mood":"melancholic cold blue"}]}'
    )


def _norm_enum(value, allowed: tuple, default: str) -> str:
    v = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return v if v in allowed else default


def _normalize_shots(shots: list, n: int) -> list[dict]:
    """길이 n 보장 + enum 보정(shot/subject/emotion) + 첫 씬 wide + 마지막 씬
    protagonist(질문 엔딩 컷) + protagonist 비중 상한 + 연속 중복 완화."""
    out: list[dict] = []
    for i in range(n):
        s = shots[i] if i < len(shots) and isinstance(shots[i], dict) else {}
        st = _norm_enum(s.get("shot_type"), _SHOT_TYPES, "wide" if i == 0 else "medium")
        subj = _norm_enum(s.get("subject_type"), _SUBJECT_TYPES, "protagonist")
        out.append({
            "shot_type": st,
            "subject_type": subj,
            "emotion": _norm_enum(s.get("emotion"), _EMOTIONS, "deadpan"),
            # two_shot 상대 역할(캐스팅 팔레트 키). two_shot 인데 미상이면 friend.
            "other_role": (
                _norm_enum(s.get("other_role"), _SUPPORT_ROLES, "friend")
                if subj == "two_shot" else ""
            ),
            # detail/mood 에서만 의미 — 곰을 작게/일부 담을지.
            "include_protagonist": bool(s.get("include_protagonist")) if subj in ("detail", "mood") else False,
            "camera_angle": str(s.get("camera_angle", "")).strip(),
            "action": str(s.get("action", "")).strip(),
            "setting": str(s.get("setting", "")).strip(),
            "mood": str(s.get("mood", "")).strip(),
        })
    # 첫 씬은 establishing wide 보장
    out[0]["shot_type"] = "wide"
    # 마지막 씬 고정: protagonist + 정면 카메라 응시(질문 엔딩 시그니처 컷)
    out[-1]["subject_type"] = "protagonist"
    if "camera" not in out[-1]["camera_angle"].lower():
        out[-1]["camera_angle"] = (
            "front-facing, looking straight into the camera, "
            "as if asking the viewer a question"
        )
    # protagonist 단독 샷 비중 상한(마지막 시그니처 컷 제외하고 초과분을 detail/mood 로 전환)
    cap = max(1, int(n * _PROTAGONIST_CAP))
    protag_idx = [i for i in range(n) if out[i]["subject_type"] == "protagonist"]
    overflow = len(protag_idx) - cap
    if overflow > 0:
        demote = ["detail", "mood"]
        k = 0
        for i in protag_idx:
            if overflow <= 0:
                break
            if i == n - 1:  # 마지막 씬은 보존
                continue
            out[i]["subject_type"] = demote[k % len(demote)]
            k += 1
            overflow -= 1
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
    subject = _norm_enum(spec.get("subject_type"), _SUBJECT_TYPES, "protagonist")
    parts = [_SHOT_PHRASE.get(st, "medium shot")]
    parts.append(_SUBJECT_PHRASE[subject])
    if spec.get("camera_angle"):
        parts.append(str(spec["camera_angle"]))
    if spec.get("action"):
        if subject in ("detail", "mood"):
            # 사물/배경 컷 — 캐릭터 주어를 붙이지 않는다(곰이 끼어들지 않도록).
            parts.append(str(spec["action"]))
        else:
            parts.append(f"the character {spec['action']}")
    if spec.get("setting"):
        parts.append(f"at {spec['setting']}")
    if spec.get("mood"):
        parts.append(str(spec["mood"]))
    emotion = _norm_enum(spec.get("emotion"), _EMOTIONS, "")
    if emotion:
        # 감정 단어만 싣는다 — 곰 표정 문구 변환(부록 D)은 PR③ 프롬프트 빌더 담당.
        parts.append(f"emotional tone: {emotion}")
    parts.append("vertical 9:16")
    composed = ", ".join(p for p in parts if p)
    return composed or fallback


def _default_shots(n: int) -> list[dict]:
    """디렉터 실패 시 안전한 기본 샷 리스트(subject_type/emotion 기본값 포함).

    첫 씬=mood(establishing), 마지막 씬=protagonist(질문 엔딩), 중간은
    protagonist/detail/mood 순환(상한 자연 충족). 감정은 deadpan 기본.
    """
    cycle = ("protagonist", "detail", "mood")
    out = []
    for i in range(n):
        if i == 0:
            subject = "mood"
        elif i == n - 1:
            subject = "protagonist"
        else:
            subject = cycle[(i - 1) % len(cycle)]
        out.append({
            "subject_type": subject, "emotion": "deadpan",
            "other_role": "", "include_protagonist": False,
        })
    return out


def apply_director(script: str, scenes: list[dict]) -> list[dict]:
    """씬 리스트에 디렉터 샷 스펙을 적용해 돌려준다.

    image_prompt 를 샷 스펙으로 구성하고, subject_type/emotion 을 씬에 붙인다
    (후속 단계가 캐릭터 레퍼런스 적용/표정 매핑에 사용). 디렉터 실패 시 기존
    image_prompt 는 유지하고 subject_type/emotion 기본값만 붙인다(안 멈춤).
    """
    if not scenes:
        return scenes
    try:
        shots = design_shots(script, scenes)
    except Exception as e:  # noqa: BLE001
        logger.warning("디렉터 단계 실패 — 기존 image_prompt + 기본 샷 리스트로 폴백: %s", e)
        defaults = _default_shots(len(scenes))
        return [
            {**s, "subject_type": d["subject_type"], "emotion": d["emotion"],
             "other_role": d["other_role"], "include_protagonist": d["include_protagonist"]}
            for s, d in zip(scenes, defaults)
        ]

    out: list[dict] = []
    for i, s in enumerate(scenes):
        spec = shots[i] if i < len(shots) else {}
        composed = compose_image_prompt(spec, fallback=str(s.get("image_prompt", "")))
        ns = dict(s)
        if composed:
            ns["image_prompt"] = composed
        ns["subject_type"] = spec.get("subject_type", "protagonist")
        ns["emotion"] = spec.get("emotion", "deadpan")
        ns["other_role"] = spec.get("other_role", "")
        ns["include_protagonist"] = bool(spec.get("include_protagonist", False))
        out.append(ns)
    return out
