"""쿠팡 상품 브랜드 명단 — 대표 2026-10-27 확정("유명 브랜드부터 보세까지, 5만~50만 원").

쿠팡 검색 API는 가격 필터가 없고 검색어당 10개만 준다. 상위는 대부분 1~3만 원대라 가격만 올리면
후보가 바닥난다 → 검색어에 브랜드명을 넣어 처음부터 그 가격대가 나오게 한다.

- A 유명·디자이너 / B 컨템·SPA / C 보세(브랜드 없이 키워드)
- 노티 나는 브랜드(30~40대 주력)·명품(쿠팡 가품·병행 위험)은 상품명에 있으면 제외
- A급은 너무 싸면 가품으로 보고 제외(BRAND_MIN)
"""

from __future__ import annotations

import random
import re

_CLOTHES = ("top", "bottoms", "dress", "outerwear")

TIERS: dict[str, dict[str, list[str]]] = {
    "A": {
        "clothes": ["마뗑킴", "마리떼 프랑소와 저버", "마르디 메크르디", "디스이즈네버댓", "커버낫", "키르시",
                    "로우클래식", "앤더슨벨", "MLB"],
        "shoes": ["나이키", "아디다스", "뉴발란스", "컨버스", "반스", "어그", "닥터마틴", "살로몬"],
        "bag": ["스탠드오일", "마르헨제이", "분크", "로우로우"],
    },
    "B": {
        "clothes": ["로엠", "미쏘", "스파오", "탑텐", "에잇세컨즈", "무신사 스탠다드 우먼", "쥬시쥬디", "플라스틱아일랜드"],
        "shoes": ["슈펜", "락피쉬웨더웨어"],
        "bag": ["조이그라이슨"],
    },
}

# 노티(30~40대 주력) + 명품(쿠팡 가품·병행수입 위험) — 상품명에 있으면 제외
EXCLUDE_BRANDS = re.compile(
    r"(\b마인\b|타임\s*옴므|\b타임\b|\b구호\b|쉬즈미스|크로커다일|올리비아\s*로렌|"
    r"구찌|프라다|디올|샤넬|루이\s*비통|에르메스|셀린|발렌시아가|생로랑|보테가|미우미우|버버리|GUCCI|PRADA|DIOR|CHANEL)",
    re.I,
)

# A급 브랜드 가품 방지 최저가(이보다 싸면 제외)
BRAND_MIN = {"shoes": 60_000, "bag": 50_000, "clothes": 40_000}


def _group(kind: str) -> str | None:
    if kind in _CLOTHES:
        return "clothes"
    return kind if kind in ("shoes", "bag") else None


def brands(tier: str, kind: str) -> list[str]:
    g = _group(kind)
    return list(TIERS.get(tier, {}).get(g, [])) if g else []


def a_brand_in(name: str, kind: str) -> str | None:
    """상품명에 들어 있는 A급 브랜드(가품 검사용)."""
    low = (name or "").lower().replace(" ", "")
    for b in brands("A", kind):
        if b.lower().replace(" ", "") in low:
            return b
    return None


def too_cheap_for_brand(name: str, price: int, kind: str) -> bool:
    g = _group(kind)
    return bool(g and a_brand_in(name, kind) and int(price or 0) < BRAND_MIN[g])


def excluded(name: str) -> bool:
    return bool(EXCLUDE_BRANDS.search(name or ""))


def mix_queries(kind: str, queries: list[str], rng: random.Random | None = None) -> list[str]:
    """테마 검색어 3개 → [A 브랜드 + 검색어1, B 브랜드 + 검색어2, 검색어3(보세)]. 브랜드가 없는 종류는 그대로.

    검색 한도(시간당 ~10회) 때문에 개수는 늘리지 않고 앞의 두 개에만 브랜드를 붙인다.
    """
    r = rng or random
    qs = [q for q in queries if q][:3]
    if not qs:
        return qs
    out = list(qs)
    for i, tier in enumerate(("A", "B")):
        pool = brands(tier, kind)
        if pool and i < len(out):
            out[i] = f"{r.choice(pool)} {out[i]}"
    return out
