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
    "허리선 오는 크롭 테일러드 재킷", "벨트·페플럼으로 허리 라인", "니트·가죽·스웨이드 텍스처 믹스",
]
AVOID = [
    "무지 맨투맨 + 레깅스 같은 운동복·잠옷 느낌 데일리룩", "번들거리는 폴리 소재", "큰 로고·캐릭터 프린트",
    "트레이닝 세트", "계절에 안 맞는 소재(가을·겨울의 린넨·시스루 단독)", "톤이 제각각인 4색 이상 조합",
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
        f"- 컬러: 베이스 2~3색({', '.join(pal['base'])}) + 포인트 최대 1색({', '.join(pal['accent'])}), 포인트는 룩의 20% 이하.",
        "- 이 계절 코디 공식: " + " / ".join(f"{f['name']}({f['hint']})" for f in formulas),
        "- 트렌드 포인트(1~2개만): " + ", ".join(TREND_POINTS),
        "- 피할 것: " + ", ".join(AVOID),
        "- 기준: 20대 한국 여성이 실제로 입고 인스타에 올릴 만한, 소재가 좋아 보이고 실루엣이 정돈된 코디.",
    ]
    return "\n".join(lines)
