"""인스타 쇼핑 — 스타일 가이드(2026-10-27 대표 승인: "준비해줘").

지그재그(카카오스타일) AI 코디처럼 **스타일별 아이템 조합표 + 컬러 가이드**를 프롬프트에 넣어
코디 품질을 올린다(추가 모델·API 없음). 쓰는 곳:
  - insta_coordi.fill_specs: 빈 종류를 채울 때 가이드를 따르게
  - insta_coordi 자동 코디: 쓸 레퍼런스가 없으면 가이드 공식으로 코디 1벌을 통째로 설계

근거(2026 FW): 코발트 블루·퍼플·버건디 포인트, 레오파드·체크 포인트 1개, 투톤(캡토) 슈즈,
크롭 테일러드 재킷, 허리 라인(벨트·페플럼), 니트·가죽·스웨이드 텍스처 믹스, 브로치·리본 포인트 1개.
(얼루어코리아 2026-08 '코발트 블루', 브런치 '26 FW 트렌드', Who What Wear 'Fall 2026' 요약)
트렌드는 시즌마다 이 파일만 고친다.
"""

from __future__ import annotations

import random

# 계절별 베이스(뉴트럴) · 포인트 컬러. 규칙: 베이스 2~3색 + 포인트 최대 1색(룩의 20% 이하).
PALETTES: dict[str, dict] = {
    "autumn": {"base": ["블랙", "차콜", "그레이", "아이보리", "베이지", "카멜", "브라운", "네이비"],
               "accent": ["코발트 블루", "버건디", "딥 퍼플", "레드", "올리브"]},
    "winter": {"base": ["블랙", "차콜", "그레이", "아이보리", "크림", "카멜", "브라운", "네이비"],
               "accent": ["버건디", "코발트 블루", "딥 그린", "레드"]},
    "spring": {"base": ["아이보리", "화이트", "베이지", "라이트 그레이", "연청", "네이비"],
               "accent": ["버터 옐로", "라벤더", "민트", "코발트 블루"]},
    "summer": {"base": ["화이트", "아이보리", "베이지", "블랙", "연청"],
               "accent": ["코발트 블루", "레몬", "코랄"]},
}

# 계절 × 생활 코디 공식. kinds 는 착장에 들어갈 종류(최대 4, 착장 참조 상한과 같게).
FORMULAS: dict[str, list[dict]] = {
    "autumn": [
        # 꾸안꾸(대표 레퍼런스 2026-10-27) — 편하게 걸친 듯 센스 있게. 생활과 맞으면 이쪽이 먼저 뽑히게 앞에 둔다.
        {"name": "니트 후드 셋업", "life": ["주말", "산책", "카페", "집"], "kinds": ["top", "bottoms", "shoes"],
         "hint": "아이보리·베이지 골지 니트 후드 + 같은 톤 니트 쇼츠(셋업) + 롱부츠 또는 워커"},
        {"name": "스트라이프 레이스 셋업", "life": ["주말", "카페", "쇼핑"], "kinds": ["top", "bottoms", "shoes"],
         "hint": "레이스 트림 스트라이프 롱슬리브 + 같은 셋업 쇼츠 + 레그워머 + 화이트 스니커즈"},
        {"name": "라글란 오프숄더", "life": ["주말", "쇼핑", "산책"], "kinds": ["top", "bottoms", "bag", "shoes"],
         "hint": "라글란 배색 오프숄더 맨투맨 + 생지 와이드 데님 + 레더 숄더백 + 스니커즈"},
        {"name": "집업 후드 레이어드", "life": ["주말", "카페", "산책"], "kinds": ["outerwear", "top", "bottoms", "shoes"],
         "hint": "블랙 집업 후드 + 화이트 골지 슬리브리스 + 와이드 데님 + 스니커즈 (비니와 잘 어울림)"},
        {"name": "블레이저 + 나시", "life": ["출근", "데이트", "카페", "약속"], "kinds": ["outerwear", "top", "bottoms", "shoes"],
         "hint": "오버핏 블랙 블레이저 + 화이트 골지 슬리브리스 + 블랙 벨트 + 연청 데님 + 로퍼"},
        {"name": "트렌치 출근룩", "life": ["출근"], "kinds": ["outerwear", "top", "bottoms", "shoes"],
         "hint": "베이지·카멜 트렌치코트 + 얇은 니트 또는 셔츠 + 와이드 슬랙스 + 로퍼"},
        {"name": "크롭 재킷 데이트룩", "life": ["데이트", "약속"], "kinds": ["outerwear", "top", "bottoms", "shoes"],
         "hint": "허리선 오는 크롭 울(트위드) 재킷 + 니트 + 미디 스커트 + 롱부츠"},
        {"name": "레더 재킷 캐주얼", "life": ["주말", "산책", "쇼핑"], "kinds": ["outerwear", "top", "bottoms", "shoes"],
         "hint": "블랙·브라운 레더 재킷 + 부드러운 니트 + 스트레이트 데님 + 앵클부츠 (니트·가죽 텍스처 믹스)"},
        {"name": "가디건 레이어드", "life": ["주말", "카페", "산책"], "kinds": ["outerwear", "top", "bottoms", "shoes"],
         "hint": "울 블렌드 가디건 + 이너 티 또는 블라우스 + 데님 + 투톤(캡토) 발레 플랫"},
        {"name": "블레이저 포인트", "life": ["출근", "전시"], "kinds": ["outerwear", "top", "bottoms", "shoes"],
         "hint": "테일러드 블레이저(허리 살짝 잡힌) + 터틀넥 + 미니 또는 미디 스커트 + 롱부츠"},
        {"name": "스웨이드 가을룩", "life": ["데이트", "카페", "전시"], "kinds": ["outerwear", "top", "bottoms", "shoes"],
         "hint": "브라운 스웨이드 재킷 + 아이보리 니트 + 플리츠 롱스커트 + 부츠"},
        {"name": "니트 원피스", "life": ["데이트", "약속"], "kinds": ["outerwear", "dress", "shoes", "bag"],
         "hint": "하프 울 코트 + 니트 원피스(벨트로 허리 라인) + 롱부츠 + 숄더백"},
        {"name": "코발트 포인트", "life": ["출근", "쇼핑", "주말"], "kinds": ["outerwear", "top", "bottoms", "shoes"],
         "hint": "그레이·블랙 모노톤에 코발트 블루 니트 하나만 포인트 + 블랙 슬랙스 + 로퍼"},
    ],
    "winter": [
        {"name": "롱코트 출근룩", "life": ["출근"], "kinds": ["outerwear", "top", "bottoms", "shoes"],
         "hint": "캐멀·차콜 롱 울코트 + 터틀넥 니트 + 슬랙스 + 앵클부츠"},
        {"name": "숏패딩 캐주얼", "life": ["주말", "산책", "쇼핑"], "kinds": ["outerwear", "top", "bottoms", "shoes"],
         "hint": "무광 숏패딩 + 니트 + 와이드 데님 + 어그 또는 스니커즈"},
        {"name": "무스탕 데이트룩", "life": ["데이트", "약속", "카페"], "kinds": ["outerwear", "top", "bottoms", "shoes"],
         "hint": "브라운 무스탕 + 니트 + 롱스커트 + 롱부츠"},
    ],
    "spring": [
        {"name": "트렌치 봄 출근", "life": ["출근"], "kinds": ["outerwear", "top", "bottoms", "shoes"],
         "hint": "라이트 트렌치 + 셔츠 + 슬랙스 + 로퍼"},
        {"name": "가디건 데이트", "life": ["데이트", "카페", "주말"], "kinds": ["outerwear", "top", "bottoms", "shoes"],
         "hint": "파스텔 가디건 + 블라우스 + 플리츠 스커트 + 메리제인"},
    ],
    "summer": [
        {"name": "셔츠 출근", "life": ["출근"], "kinds": ["top", "bottoms", "shoes", "bag"],
         "hint": "코튼 셔츠 + 와이드 슬랙스 + 샌들 또는 로퍼 + 토트백"},
        {"name": "원피스 주말", "life": ["주말", "데이트", "카페"], "kinds": ["dress", "shoes", "bag"],
         "hint": "코튼 미디 원피스 + 샌들 + 라탄 또는 캔버스백"},
    ],
}

TREND_POINTS = [
    "코발트 블루·퍼플·버건디 중 포인트 1색", "레오파드 또는 체크 포인트 아이템 1개까지", "투톤(캡토) 슈즈",
    "허리선 오는 크롭 테일러드 재킷", "벨트로 허리 라인", "니트·가죽·스웨이드 텍스처 믹스", "셋업(같은 톤 상하의)",
]
# 꾸안꾸 기준(대표 2026-10-27): 센스 있게, 과하게 꾸미지 않기. 채이는 몸매가 좋아 실루엣이 드러나는 핏을 살린다
# (골지 나시·슬림 니트·오프숄더·허리 라인) — 단, 노골적인 노출·몸매 강조 구도는 아님.
TONE = ("꾸안꾸 — 대충 걸친 듯하지만 센스 있는 데일리룩. 셋업·레이어드·배색 하나로 포인트. "
        "실루엣이 자연스럽게 드러나는 핏(골지 나시, 슬림 니트, 오프숄더, 벨트 허리 라인)을 살리고 노골적인 노출은 피한다.")
ACCESSORIES = ["얇은 실버·골드 목걸이", "작은 후프 귀걸이", "선글라스", "비니", "레그워머", "레더 숄더백"]
AVOID = [
    "무지 맨투맨 + 레깅스 같은 운동복·잠옷 느낌", "번들거리는 폴리 소재", "큰 캐릭터 프린트",
    "트레이닝 세트", "계절에 안 맞는 소재(가을·겨울의 린넨·시스루 단독)", "톤이 제각각인 4색 이상 조합",
    "진주 롱목걸이·브로치 등 과한 액세서리", "정장처럼 각 잡힌 과한 차림",
]


def _life_words(life: str | None) -> list[str]:
    return [w.strip() for w in (life or "").replace("+", " ").replace("·", " ").split() if w.strip()]


def pick_formula(season: str, life: str | None = None, rng: random.Random | None = None,
                 avoid_names: list[str] | None = None) -> dict:
    """계절·생활에 맞는 공식 1개. 생활이 맞는 공식 우선, 최근 쓴 이름은 피한다."""
    r = rng or random
    pool = FORMULAS.get(season) or FORMULAS["autumn"]
    words = _life_words(life)
    fit = [f for f in pool if any(w in lf for w in words for lf in f["life"])] or pool
    fresh = [f for f in fit if f["name"] not in set(avoid_names or [])] or fit
    return r.choice(fresh)


def guide_text(season: str, life: str | None = None) -> str:
    """프롬프트에 넣을 가이드(한국어). 컬러 규칙 · 이 계절 공식 · 트렌드 포인트 · 피할 것."""
    pal = PALETTES.get(season) or PALETTES["autumn"]
    formulas = FORMULAS.get(season) or FORMULAS["autumn"]
    lines = [
        f"[스타일 가이드 · {season}" + (f" · {life}" if life else "") + "]",
        f"- 톤: {TONE}",
        "- 액세서리(1~2개만): " + ", ".join(ACCESSORIES),
        f"- 컬러: 베이스 2~3색({', '.join(pal['base'])}) + 포인트 최대 1색({', '.join(pal['accent'])}), 포인트는 룩의 20% 이하.",
        "- 이 계절 코디 공식: " + " / ".join(f"{f['name']}({f['hint']})" for f in formulas),
        "- 트렌드 포인트(1~2개만): " + ", ".join(TREND_POINTS),
        "- 피할 것: " + ", ".join(AVOID),
        "- 기준: 20대 한국 여성이 실제로 입고 인스타에 올릴 만한 꾸안꾸 — 소재가 좋아 보이고 실루엣이 정돈된 코디.",
    ]
    return "\n".join(lines)
