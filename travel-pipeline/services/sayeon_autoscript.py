"""사연 트랙 — 자동 사연 생성 (auto-script).

버튼 한 번으로 '도파민 도는' 1인칭 한국어 감성 사연을 자동 작성한다. gpt-4o-mini 1회
(JSON 모드, 동기). 주제 풀에서 랜덤 선택(또는 입력 topic) + 화자 설정(캐릭터 gender/age)
을 반영하고, 매번 다른 주제·반전으로 다양성을 확보한다.

출력 script(여러 줄)는 그대로 대본 칸에 채워지고, 이후 split_script 가 씬으로 쪼갠다.
"""

from __future__ import annotations

import json
import logging
import os
import random

from openai import OpenAI

from services.sayeon_formulas import select_for_concept

logger = logging.getLogger(__name__)

# 기본값 = 현재 동작 그대로(플래그 미설정 시 v1·gpt-4o-mini·temp 0.95 유지).
# Railway env 로만 켜고/끄고/롤백한다(코드 머지만으론 동작 불변).
_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_TEMPERATURE = "0.95"
# 폭주·잘림 방지 가드(300~360자 사연 + JSON 여유에 충분). 상수.
_MAX_TOKENS = 900

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


# v2 에서만 추가되는 [흐름] 블록(매끄러운 연결·인과). v1 은 이 블록 없이 그대로.
_FLOW_BLOCK_V2 = (
    "[흐름 — 매끄러운 연결]\n"
    "- 줄과 줄 사이를 자연스럽게 이어라. 갑작스러운 화제 전환·논리 비약 금지 — 앞 줄의 "
    "감정/상황을 받아 다음 줄로 매끄럽게 넘어간다.\n"
    "- 각 전개가 '왜' 일어났는지 바로 앞 줄에서 납득되게, 인과를 분명히 한다.\n"
)
# 삽입 기준점([길이] 블록 바로 앞). v2/v3 일 때 그 앞에 블록을 끼운다.
_LENGTH_ANCHOR = "[길이 — 약 90초]\n"

# v3 에서만 추가되는 [도파민] 규칙 블록(작업지시서 3단계). v1/v2 는 이 블록 없이 그대로.
_DOPAMINE_BLOCK_V3 = (
    "[도파민 — v3]\n"
    "- 훅(첫 1~2문장)=정보 격차: 충격적 결과를 먼저 흘리고 원인·전말은 뒤로 미룬다.\n"
    "- 공분 포인트: 빌런이 '선을 넘는 결정적 한마디/행동'을 최소 1개 분명히 박는다.\n"
    "- 다단계 에스컬레이션: 갈등을 최소 2번 고조시킨다(중간에 한 번 더 뒤집기).\n"
    "- 구체 디테일: 숫자·기간·실제 대사로 현실성(예: 200만원, 3년, 읽씹 5일).\n"
    "- 엔딩 의도: 사이다(통쾌) 또는 고구마(여운) 중 하나를 분명히 잡는다 "
    "(마지막 줄의 형식 — 질문/평서 — 은 본문의 엔딩 규칙을 따른다).\n"
    "- 금지선: 욕설·선정성·혐오·잔혹묘사·실명·특정집단 비하 금지. 자극은 공분·반전·정보격차로만.\n"
)


# 마지막 '시청자 질문' 엔딩 포함 확률(코드 주사위). 0.30 = 30% 포함 / 70% 생략.
# 포함 시 GPT 가 사연 맥락에 맞춰 매번 다른 질문 1줄 생성(고정 문장 아님), 생략 시 평서 마무리.
INCLUDE_CLOSING_Q_PROB = 0.30


def _build_system_prompt(
    speaker: str, formula_name: str, formula_desc: str, prompt_version: str = "v1",
    include_closing_q: bool = True,
) -> str:
    # 엔딩 모드 — 마지막 시청자 질문 포함/생략. 생략 시 사연의 마지막 문장으로 자연 마무리.
    if include_closing_q:
        _end_term = "- (단, 마지막 질문 엔딩은 '~요?' 의문형으로 끝내도 된다.)\n"
        _end_anchor = '- 질문 엔딩 바로 앞에도 공감 유도 문장을 1줄 넣는다("여러분은 이런 적 없어요?" 류).\n'
        _end_rule = (
            "- **질문 엔딩 고정**: 마지막 줄은 시청자에게 판결을 묻는 문장으로 끝낸다 "
            '("여러분이라면 어떻게 하셨을 것 같아요?" 류 — 매번 표현을 변주).\n'
        )
        _end_example = "\\n(반전 또는 사이다)...\\n여러분은 이런 적 없어요?\\n시청자 판결 질문?"
    else:
        _end_term = "- (마지막 줄도 평서 구어체로 자연스럽게 — 시청자에게 묻는 질문으로 끝내지 않는다.)\n"
        _end_anchor = '- 본문 마지막 부분에도 공감 유도 문장을 1줄 넣되, 질문으로 끝내지는 않는다.\n'
        _end_rule = (
            "- **질문 없는 자연 마무리**: 마지막 줄은 사연의 여운·감정이 남는 평서 구어체 문장으로 "
            "자연스럽게 끝낸다. ⚠️ 시청자에게 묻는 질문·판결 요청·'여러분이라면?' 류로 끝내지 말 것.\n"
        )
        _end_example = "\\n(반전 또는 사이다)...\\n그날 일은 아직도 잊히지가 않더라고."
    base = (
        "너는 한국 숏폼 '사연' 채널의 1급 작가다. AI 티가 전혀 안 나게, 진짜 사람이 자기 "
        "경험을 털어놓는 **1인칭 고백체** 한국어 입말로 사연을 쓴다. 목표는 도파민·체류시간·댓글이다.\n\n"
        "[톤 — 사실성]\n"
        "- 1인칭 고백체. 친구에게 실제로 털어놓듯 자연스러운 구어체. 매끈한 완성형 문장만 "
        '늘어놓지 말고 짧은 문장·망설임·끊김을 섞는다(예: "그런데… 그때 알았어.").\n'
        "- 감정은 '슬펐다'처럼 설명하지 말고 상황·행동으로 보여준다(show, don't tell).\n"
        "- 클리셰·번역체·과장·해시태그·이모지 금지.\n"
        "[말끝 — 자연스러운 입말 (필수)]\n"
        "- ⚠️ 문어체/서술체 종결 금지: '~다'로 끝나는 평서문 금지(예: '~했다/~이다/~한다/"
        "~였다/~같다' 전부 금지).\n"
        "- 친구에게 털어놓는 구어체 종결어미만 사용한다: "
        "~거야 / ~더라고 / ~잖아 / ~는 거지 / ~었어(~았어) / ~거든 / ~더라니까 / "
        "~말이야 / ~이었거든 / ~했다니까.\n"
        "- 같은 종결어미를 3회 이상 연속으로 쓰지 말 것 — 어미를 계속 변주한다.\n"
        f"{_end_term}"
        "[시작 멘트 — 도입 1문장]\n"
        "- 첫 문장은 친구를 부르듯 가볍게 운을 떼는 **짧은 도입 1문장**으로 연다 "
        '(예: "오늘은 진짜 충격받은 일 얘기해줄게", "오늘은 내가 겪은 황당한 일 들어봐", '
        '"나 최근에 진짜 어이없는 일이 있었거든").\n'
        "- ⚠️ 도입 문구는 매번 다르게 — 위 예시를 그대로 베끼지 말고 새로 짓는다(고정 문구 금지).\n"
        "- **도입 바로 다음 문장(둘째 줄)부터 사건의 한복판**으로 진입한다(자기소개·배경 설명 금지).\n"
        "[갈등 공식 — 뼈대]\n"
        f"- 이번 사연은 '{formula_name}' 공식을 뼈대로 한다: {formula_desc}.\n"
        "- ⚠️ 특정 커뮤니티/실제 글을 복제·변형하지 말 것. 위 공식은 '구조'만 빌리고 "
        "인물·상황·디테일은 전부 새로 지어낸다(완전 창작).\n"
        "[공감 + 감정 밀도 — 시청자가 '내 얘기 같다', '진짜 열받아' 느끼게]\n"
        "- 보편적 감정을 추상어가 아니라 **구체적 상황**으로 표현한다:\n"
        '  · 배신감 → "2년을 믿었는데", "내가 제일 힘들 때 걔가".\n'
        '  · 억울함 → "내가 뭘 잘못한 건지", "어이가 없어서 말도 안 나오더라고".\n'
        '  · 허탈함 → "그냥 웃음이 나왔어", "힘이 쭉 빠지는 느낌?".\n'
        "- 이런 **공감 유도 감정 묘사를 최소 2회 이상** 본문에 녹인다.\n"
        "- **감정 폭발 포인트 1개 필수**: 시청자가 '진짜 열받아/소름' 할 반전 디테일을 "
        "한 번은 정확히 찍는다(상대의 결정적 한마디·행동).\n"
        "- **댓글 유발**: 판단이 갈리거나 분노가 치미는 지점을 남겨 댓글을 쓰게 만든다.\n"
        "- **공감 앵커 2개 이상**: 본문 중간에 시청자에게 말 거는 문장을 2번 이상 넣는다 "
        '("나만 이런 거 아니잖아요?", "이런 경험 한 번쯤 있지 않아요?" 류 — 표현 변주).\n'
        f"{_end_anchor}"
        "[구조 — 도파민]\n"
        "- **에스컬레이션 필수**: 중반에 상황이 '한 번 더 나빠지는' 전개를 최소 1회 넣는다.\n"
        "- **구체적 숫자 필수**: 금액·기간·횟수를 정확한 수치로 박는다 "
        '(예: "200만원", "3년", "7번이나 연락", "카톡 5일째 읽씹").\n'
        '- ⚠️ 추상적 표현 금지: "많은 돈", "오랜 친구", "여러 번" 같은 뭉뚱그린 말 금지 — '
        "반드시 숫자로 바꾼다.\n"
        "- **배신 디테일(해당 공식이면)**: 빌려주거나 믿어줄 '당시 상황'을 한 줄로 그리고, "
        "배신자의 **뻔뻔한 행동을 최소 1개** 구체적으로 보여준다.\n"
        "- **결말**: 반전 또는 사이다 중 1개를 반드시 넣는다.\n"
        f"{_end_rule}"
        "[길이 — 약 90초]\n"
        "- 낭독 시 약 90초 분량: 한국어 대략 300~360자, 12~16개의 짧고 자연스러운 문장/비트 "
        "(도입 1문장 + 공감 유도 문장 포함).\n"
        "- 한 줄 = 하나의 짧은 호흡/장면. 줄바꿈(\\n)으로 구분한다.\n"
        "[기타]\n"
        "- 출력은 오직 JSON 객체 하나. 마크다운/설명 금지.\n"
        f"- 화자(1인칭 '나')는 {speaker} 로 고정. 말투·시점을 끝까지 일관되게 유지한다.\n"
        "- 자극적이되 선정적이지 않게. 실명·특정 브랜드·혐오·민감정보 금지.\n"
        "- title: 썸네일용 후킹 제목. 짧고 강하게(12자 내외) 궁금증 유발, 스포일러 금지.\n\n"
        "[출력 형식]\n"
        '{"script":"오늘은 ~ 얘기해줄게(도입)...\\n(사건 한복판)...\\n...(중반 에스컬레이션)...'
        f'{_end_example}",'
        '"title":"강한 후킹 제목"}\n'
        "script 는 줄바꿈(\\n)으로 구분된 12~16줄 한 문자열."
    )
    # v1 문자열은 그대로 두고, [길이] 블록 앞에 버전별 블록을 삽입.
    if prompt_version in ("v2", "v3"):
        base = base.replace(_LENGTH_ANCHOR, _FLOW_BLOCK_V2 + _LENGTH_ANCHOR, 1)
    if prompt_version == "v3":
        base = base.replace(_LENGTH_ANCHOR, _DOPAMINE_BLOCK_V3 + _LENGTH_ANCHOR, 1)
    return base


def generate_script(topic: str = "", character: dict | None = None) -> dict:
    """랜덤(또는 지정) 주제로 1인칭 감성 사연을 생성한다.

    Returns: {"script": str(여러 줄), "title": str, "topic": str}
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 미설정 — 사연을 생성할 수 없습니다.")

    speaker = _speaker_hint(character)

    # 품질·다양성 플래그(전부 env, 기본값=현재 동작). 롤백 = env 원복/삭제 후 재시작.
    model = (os.getenv("SAYEON_SCRIPT_MODEL") or _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
    try:
        temperature = float(os.getenv("SAYEON_SCRIPT_TEMPERATURE") or _DEFAULT_TEMPERATURE)
    except ValueError:
        temperature = float(_DEFAULT_TEMPERATURE)
    prompt_version = (os.getenv("SAYEON_SCRIPT_PROMPT_VERSION") or "v1").strip() or "v1"
    formula_mode = (os.getenv("SAYEON_FORMULA_MODE") or "legacy").strip().lower()
    try:
        antirepeat_n = int(os.getenv("SAYEON_FORMULA_ANTIREPEAT_N") or "5")
    except ValueError:
        antirepeat_n = 5

    # 컨셉 기반 선택: FORMULA_MODE=concept + topic 이 9컨셉 키일 때만(produce-due/pick-topic 이
    # 컨셉을 topic 으로 그대로 넘김). 그 외엔 legacy(현재 동작 100% 보존).
    selected = select_for_concept(topic, antirepeat_n) if formula_mode == "concept" else None
    if selected:
        formula_desc_text, subtopic = selected
        formula_name = (topic or "").strip()  # 프롬프트 '공식' 라벨 = 컨셉명
        formula_desc = formula_desc_text       # 선택된 공식 뼈대
        chosen = subtopic                      # 소재 결 = 서브토픽(컨셉 디테일 강화)
        ret_formula = formula_desc_text        # 반환 formula = 선택된 공식 문자열
        logger.info(
            "[autoscript] concept=%s formula=%r subtopic=%r (antirepeat_n=%d, prompt=%s)",
            formula_name, formula_desc_text, subtopic, antirepeat_n, prompt_version,
        )
    else:
        # legacy — 현재 동작 그대로.
        chosen = topic.strip() or random.choice(_TOPIC_POOL)
        formula_name, formula_desc = random.choice(_CONFLICT_FORMULAS)  # 갈등 공식 뼈대(부록 E)
        ret_formula = formula_name

    # 마지막 시청자 질문 엔딩: 코드 주사위로 30% 포함 / 70% 생략(고정 문장 아님 — 포함 시 맥락형).
    include_closing_q = random.random() < INCLUDE_CLOSING_Q_PROB

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": _build_system_prompt(
                    speaker, formula_name, formula_desc, prompt_version,
                    include_closing_q=include_closing_q,
                ),
            },
            {
                "role": "user",
                "content": (
                    f"갈등 공식: '{formula_name}'. 소재 결: '{chosen}'. 위 규칙대로 이 공식을 "
                    "뼈대로 매번 다른 인물·설정·반전으로 완전히 새로 창작해 JSON 으로 써라."
                ),
            },
        ],
        response_format={"type": "json_object"},
        temperature=temperature,  # 기본 0.95(현재) — SAYEON_SCRIPT_TEMPERATURE 로 조정
        max_tokens=_MAX_TOKENS,  # 폭주·잘림 방지 가드
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
        "formula": ret_formula,  # 사용한 갈등 공식(legacy=이름 / concept=선택된 공식 문자열)
    }
