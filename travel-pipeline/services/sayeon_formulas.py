"""사연 대본 v3 — 컨셉별 갈등 공식 + 서브토픽 풀 (스토리 다양성).

컨셉 키는 content_plans.concept (= src/lib/content-plan.ts CONTENT_CONCEPTS) 와
동일 문자열을 쓴다: 가족 / 이별 / 복수 / 우정/배신 / 연애 / 직장/돈 / 감동 / 반전 / 기타.

select_for_concept(concept, antirepeat_n) 가 (공식, 서브토픽) 1쌍을 고른다. 최근 N개에
쓰인 공식·서브토픽은 후보에서 제외(중복방지) 후 랜덤, 고갈되면 전체 풀에서 랜덤(graceful).
최근 사용 기록은 프로세스 메모리(Railway 단일 프로세스)에 둔다 — 신규 테이블 없음.
"""

from __future__ import annotations

import random
import threading

# 컨셉 → 갈등 공식(뼈대) 목록. (작업지시서 1단계 1~41)
CONCEPT_FORMULAS: dict[str, list[str]] = {
    "가족": [
        "한 자식만 편애·나에게만 희생 강요 → 쌓인 게 터짐",
        "형제가 유산·재산을 거짓말·공작으로 가로챔",
        "평생 효도했는데 부모는 무책임한 자식을 더 챙김",
        "부모가 본인 체면 때문에 내 인생(결혼·직업)을 통제·간섭",
        "'가족이니까' 내 돈을 당연하게 요구하고 안 갚음",
        "가족 행사에서 나만 투명인간 → 결정적 한마디에 폭발",
        "명절·제사·살림 노동을 한 사람(며느리 등)에게만 전가",
        "시부모/처가가 신혼집·육아에 과도하게 개입·통제",
        "부모 부양·요양을 두고 형제끼리 책임 떠넘기기",
        "어려울 때 외면하던 가족이 내가 잘되자 손 벌림",
    ],
    "직장/돈": [
        "상사가 내 성과·공로를 가로채 본인 것으로 보고",
        "동료가 험담·모함·라인으로 나를 깎아내림",
        "부당한 업무를 떠넘기고 잘못은 나에게 뒤집어씌움",
        "토사구팽 — 이용만 하고 위기 때 버림",
        "빌려준 돈을 안 갚고 오히려 큰소리치는 지인",
        "동업·투자·보증에서 믿었던 사람이 돈을 빼돌리거나 떠넘김",
    ],
    "우정/배신": [
        "절친이 내 비밀·약점을 이용하거나 퍼뜨림",
        "친구가 내 연인·기회·물건을 가로챔",
        "어려울 때만 찾고 좋을 때 외면하는 가짜 우정",
        "배우자·연인이 가까운 사람과 불륜·환승(믿음의 배신)",
        "믿었던 사람이 뒤에서 나를 속이고 있었음",
    ],
    "이별": [
        "결혼 직전 상대(또는 그 가족)의 충격적 본모습 → 파혼",
        "헌신했던 연인의 일방적·냉정한 이별 통보",
        "조건·돈 문제(반반결혼 등)로 갈라선 관계",
        "이별 후 상대가 뒤늦게 후회하며 매달림",
    ],
    "연애": [
        "내 돈·시간만 이용하고 중요할 땐 없던 연인",
        "좋은 사람인 척했지만 결정적 거짓말이 드러난 상대",
        "썸·짝사랑의 반전(예상 못한 진심 또는 충격)",
        "데이트·결혼 준비에서 드러나는 가치관 충돌",
    ],
    "반전": [
        "평범해 보이던 인물의 충격적 정체가 드러남(회장 위장 등)",
        "무시당하던 사람이 알고 보니 결정적 키를 쥐고 있었음",
        "선의·헌신의 진짜 동기·결말이 끝에서 뒤집힘",
        "가해자인 줄 알았던 사람이 사실은 피해자(또는 반대)",
        "오랜 비밀·오해가 마지막에 풀리며 의미가 완전히 바뀜",
    ],
    "복수": [
        "나를 무시·이용한 사람이 인과응보로 무너짐",
        "참다 참다 한 방에 통쾌하게 되갚음",
        "가해자가 자기 함정에 스스로 빠짐(자업자득)",
    ],
    "감동": [
        "대가 없이 베푼 선의가 예상 못한 방식으로 돌아옴",
        "약자를 지킨 작은 용기·오랜 오해의 화해가 큰 울림",
    ],
    "기타": [
        "상식 밖 행동을 당당히 하는 몰상식 인물(적반하장·피해자 코스프레)",
        "반복되는 수상한 손님/인물의 충격적 정체(미스터리 훅)",
    ],
}

# 컨셉 → 서브토픽(소재 결) 풀.
CONCEPT_SUBTOPICS: dict[str, list[str]] = {
    "가족": ["유산·상속", "부모 부양·요양", "결혼식 비용·혼수", "손주 양육", "명절·제사", "형제 차별", "가족 단톡방", "김장·살림"],
    "직장/돈": ["성과·승진", "회식·야근", "사내 정치·라인", "업무 떠넘기기", "퇴사·이직", "빌린 돈", "동업·투자", "보증·명의", "경조사비"],
    "우정/배신": ["돈거래", "비밀 누설", "연인 가로채기", "불륜·환승", "모임·단톡", "오랜 절교"],
    "이별": ["파혼", "결혼 조건", "상견례", "환승 이별", "장거리·연락"],
    "연애": ["데이트 비용", "가치관 충돌", "전 연인", "썸·짝사랑", "거짓말·이중생활"],
    "반전": ["정체·위장 폭로", "신분 격차", "동기 반전", "가해자·피해자 뒤집기", "비밀 공개"],
    "복수": ["직장 빌런", "갑질 손님·거래처", "무례한 이웃", "사기꾼", "차별한 사람"],
    "감동": ["낯선 이의 친절", "가족 화해", "은인 재회", "반려동물", "작은 선행"],
    "기타": ["무개념 이웃·진상", "민폐 친척", "적반하장 가해자", "미스터리 정체", "어이없는 요구"],
}


def has_concept(concept: str) -> bool:
    return concept in CONCEPT_FORMULAS and concept in CONCEPT_SUBTOPICS


# ── 최근 사용 추적(프로세스 메모리, 중복방지) ───────────────────────
_lock = threading.Lock()
_recent_formulas: dict[str, list[str]] = {}
_recent_subtopics: dict[str, list[str]] = {}


def _pick(pool: list[str], recent: list[str], n: int) -> str:
    """최근 n개(recent 끝부분) 제외 후 랜덤. 후보 고갈 시 전체 풀에서 랜덤."""
    if n > 0 and recent:
        candidates = [x for x in pool if x not in recent[-n:]]
    else:
        candidates = list(pool)
    if not candidates:
        candidates = list(pool)
    return random.choice(candidates)


def select_for_concept(concept: str, antirepeat_n: int = 5) -> tuple[str, str] | None:
    """(공식, 서브토픽) 1쌍 선택. concept 미매핑/빈값이면 None(호출부가 legacy 폴백)."""
    concept = (concept or "").strip()
    if not has_concept(concept):
        return None
    formulas = CONCEPT_FORMULAS[concept]
    subtopics = CONCEPT_SUBTOPICS[concept]
    with _lock:
        rf = _recent_formulas.setdefault(concept, [])
        rs = _recent_subtopics.setdefault(concept, [])
        formula = _pick(formulas, rf, antirepeat_n)
        subtopic = _pick(subtopics, rs, antirepeat_n)
        if antirepeat_n > 0:
            rf.append(formula)
            rs.append(subtopic)
            _recent_formulas[concept] = rf[-antirepeat_n:]
            _recent_subtopics[concept] = rs[-antirepeat_n:]
    return formula, subtopic
