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

# 랜덤 주제 풀 — 자극적이되 선정적이지 않게, 감성·반전 여지가 큰 소재.
_TOPIC_POOL = [
    "가족의 숨겨진 비밀",
    "배신, 그리고 뒤늦은 용서",
    "헤어졌던 첫사랑과의 재회",
    "평생 후회로 남은 선택",
    "사소한 오해로 영영 잃은 인연",
    "한참 뒤에야 알게 된 진실",
    "끝내 전하지 못한 고백",
    "부모의 말 없는 희생",
    "조부모와의 마지막 추억",
    "낯선 사람에게 받은 뜻밖의 호의",
    "갑작스러운 이별과 상실",
    "형제·자매 사이의 미안함과 고마움",
    "가난했지만 따뜻했던 어린 시절",
    "철없던 시절의 후회",
]

# 갈등 공식 라이브러리(부록 E). 사연마다 1개를 뼈대로 골라 '공식 기반 완전 창작'한다.
# (특정 커뮤니티 글 복제·변형 금지 — 구조만 빌리고 내용은 새로 지어낸다.)
_CONFLICT_FORMULAS = [
    ("배신", "가장 믿었던 사람(연인·절친·가족)이 뒤통수를 친다 — 거짓·배신이 드러남"),
    ("시댁·처가", "무리한 요구 + 배우자의 방관 — 통장 요구, 명절 차별 등"),
    ("돈", "빌려준 돈·축의금·유산 분쟁 — 인색하거나 뻔뻔한 상대 (예: 5만원 내고 4인분)"),
    ("직장 빌런", "공 가로채기·뒷담화가 들통난다 — 회식/회의에서 폭로"),
    ("역전·사이다", "무시당하던 주인공의 반격 — 알고 보니 실세/건물주 등"),
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


def _build_system_prompt(speaker: str, formula_name: str, formula_desc: str) -> str:
    return (
        "너는 한국 숏폼 '사연' 채널의 1급 작가다. AI 티가 전혀 안 나게, 진짜 사람이 자기 "
        "경험을 털어놓는 **1인칭 고백체** 한국어 입말로 사연을 쓴다. 목표는 도파민·체류시간·댓글이다.\n\n"
        "[톤 — 사실성]\n"
        "- 1인칭 고백체. 친구에게 실제로 털어놓듯 자연스러운 구어체. 매끈한 완성형 문장만 "
        '늘어놓지 말고 짧은 문장·망설임·끊김을 섞는다(예: "그런데… 그때 알았어.").\n'
        "- 감정은 '슬펐다'처럼 설명하지 말고 상황·행동으로 보여준다(show, don't tell).\n"
        "- 클리셰·번역체·과장·해시태그·이모지 금지.\n"
        "[갈등 공식 — 뼈대]\n"
        f"- 이번 사연은 '{formula_name}' 공식을 뼈대로 한다: {formula_desc}.\n"
        "- ⚠️ 특정 커뮤니티/실제 글을 복제·변형하지 말 것. 위 공식은 '구조'만 빌리고 "
        "인물·상황·디테일은 전부 새로 지어낸다(완전 창작).\n"
        "[구조 — 도파민]\n"
        "- 첫 줄(3초 훅): **사건의 한복판**에서 시작한다. 자기소개·배경 설명으로 시작 금지 "
        '(예: "남편 휴대폰에서 모르는 여자 사진이 나왔습니다.").\n'
        "- **에스컬레이션 필수**: 중반에 상황이 '한 번 더 나빠지는' 전개를 최소 1회 넣는다.\n"
        "- **디테일 리얼리즘**: 구체적 숫자·고유 디테일을 박는다(금액·기간·읽씹 일수·시각 등, "
        '예: "3년 만에", "500만원", "카톡을 5일째 읽씹").\n'
        "- **결말**: 반전 또는 사이다 중 1개를 반드시 넣는다.\n"
        "- **질문 엔딩 고정**: 마지막 줄은 시청자에게 판결을 묻는 문장으로 끝낸다 "
        '("여러분이라면 어떻게 하셨을 것 같아요?" 류 — 매번 표현을 변주).\n'
        "[길이 — 약 90초]\n"
        "- 낭독 시 약 90초 분량: 한국어 대략 300~360자, 12~16개의 짧고 자연스러운 문장/비트.\n"
        "- 한 줄 = 하나의 짧은 호흡/장면. 줄바꿈(\\n)으로 구분한다.\n"
        "[기타]\n"
        "- 출력은 오직 JSON 객체 하나. 마크다운/설명 금지.\n"
        f"- 화자(1인칭 '나')는 {speaker} 로 고정. 말투·시점을 끝까지 일관되게 유지한다.\n"
        "- 자극적이되 선정적이지 않게. 실명·특정 브랜드·혐오·민감정보 금지.\n"
        "- title: 썸네일용 후킹 제목. 짧고 강하게(12자 내외) 궁금증 유발, 스포일러 금지.\n\n"
        "[출력 형식]\n"
        '{"script":"3초 훅 첫 줄...\\n...(중반 에스컬레이션)...\\n(반전 또는 사이다)...'
        '\\n시청자 판결 질문?","title":"강한 후킹 제목"}\n'
        "script 는 줄바꿈(\\n)으로 구분된 12~16줄 한 문자열."
    )


def generate_script(topic: str = "", character: dict | None = None) -> dict:
    """랜덤(또는 지정) 주제로 1인칭 감성 사연을 생성한다.

    Returns: {"script": str(여러 줄), "title": str, "topic": str}
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 미설정 — 사연을 생성할 수 없습니다.")

    chosen = topic.strip() or random.choice(_TOPIC_POOL)
    formula_name, formula_desc = random.choice(_CONFLICT_FORMULAS)  # 갈등 공식 뼈대(부록 E)
    speaker = _speaker_hint(character)
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=_OPENAI_MODEL,
        messages=[
            {"role": "system", "content": _build_system_prompt(speaker, formula_name, formula_desc)},
            {
                "role": "user",
                "content": (
                    f"갈등 공식: '{formula_name}'. 소재 결: '{chosen}'. 위 규칙대로 이 공식을 "
                    "뼈대로 매번 다른 인물·설정·반전으로 완전히 새로 창작해 JSON 으로 써라."
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
        "formula": formula_name,  # 사용한 갈등 공식(추적용)
    }
