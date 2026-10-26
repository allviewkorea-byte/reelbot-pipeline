"""캐릭터 실측 치수 — 스튜디오 bible.measurements (A2 0-1, 테이블 구조 변경 없음).

착장 핏은 "예쁘게"가 아니라 "계산대로"(대표 지시): 모델 실측 치수 × 상품 사이즈표로 기장·여유·어깨선을
계산해 사실 문장으로 프롬프트에 넣는다(A2-3). 그 계산의 입력이 이 치수다.
- 저장: studio_characters.bible["measurements"] = {height, shoulder, …, size_top, size_bottom, size_shoes}
- 채이 기본값은 대표 확정 전 초안 — 화면에 '초안'으로 보여 주고, 저장하기 전에는 착장 생성을 막는다.
"""

from __future__ import annotations

from services import character_studio as cs

# key → (한글, 최소, 최대) — cm
NUMERIC: dict[str, tuple[str, float, float]] = {
    "height": ("키", 120, 220),
    "shoulder": ("어깨너비", 25, 60),
    "chest": ("가슴둘레", 60, 140),
    "waist": ("허리둘레", 45, 130),
    "hip": ("엉덩이둘레", 60, 150),
    "arm": ("팔길이", 40, 85),
    "inseam": ("다리안쪽길이", 55, 100),
}
SIZES: dict[str, str] = {"size_top": "상의 사이즈", "size_bottom": "하의 사이즈", "size_shoes": "신발 사이즈"}

# 채이 초안(대표 확정 전, 화면에서 수정)
DRAFTS: dict[str, dict] = {
    "chaei": {"height": 172, "shoulder": 38, "chest": 86, "waist": 63, "hip": 91, "arm": 58, "inseam": 80,
              "size_top": "S~M(55)", "size_bottom": "S(26)", "size_shoes": "240"},
}


def fields() -> list[dict]:
    return ([{"key": k, "label": v[0], "unit": "cm", "min": v[1], "max": v[2]} for k, v in NUMERIC.items()]
            + [{"key": k, "label": v, "unit": ""} for k, v in SIZES.items()])


def saved(char: dict) -> dict | None:
    m = (char.get("bible") or {}).get("measurements")
    return m if isinstance(m, dict) and all(m.get(k) for k in NUMERIC) else None


def get(character_id: str) -> dict:
    """{values, saved: bool, draft: bool, fields}. 저장 전이면 초안(있을 때)을 values 로."""
    char = cs.get_character(character_id)
    m = saved(char)
    if m:
        return {"values": m, "saved": True, "draft": False, "fields": fields()}
    draft = DRAFTS.get(char["id"])
    return {"values": dict(draft) if draft else {}, "saved": False, "draft": bool(draft), "fields": fields()}


def validate(values: dict) -> dict:
    out: dict = {}
    for k, (label, lo, hi) in NUMERIC.items():
        try:
            v = float(values.get(k))
        except (TypeError, ValueError):
            raise cs.StudioError(f"{label}를 숫자로 입력해 주세요.") from None
        if not lo <= v <= hi:
            raise cs.StudioError(f"{label}는 {lo:g}~{hi:g}cm 사이로 입력해 주세요.")
        out[k] = round(v, 1)
    for k, label in SIZES.items():
        s = str(values.get(k) or "").strip()
        if len(s) > 20:
            raise cs.StudioError(f"{label}는 20자 이내로 적어 주세요.")
        out[k] = s
    return out


def save(character_id: str, values: dict) -> dict:
    char = cs.get_character(character_id)
    m = validate(values)
    bible = {**(char.get("bible") or {}), "measurements": m}
    cs.upsert_character(char["id"], char["name"], bible=bible)
    return {"values": m, "saved": True, "draft": False, "fields": fields()}
