"""쇼츠 장면 레퍼런스 선택 — 등장 인물 → 확정 캐스트의 **라벨 기준** 이미지(최대 7장) + 외형 텍스트.

Kling O3 Reference(WaveSpeed)는 레퍼런스 이미지 최대 7장(영상 레퍼런스 없을 때). 우선순위(0단계 승인):
1. 인물마다 기준 얼굴(face) + 전신 정면(front)        ← 얼굴·옷 고정의 핵심
2. 2인 이상이면 가족 단체(group, 키 비율 기준) — 마지막 편은 돌잔치 의상 단체(finale)가 있으면 그것
3. 남는 칸: 주인공(첫 인물)부터 돌아가며 장면용 이미지(B=액션, A=표정, 그 외=반측면/측면)
엄마 단계: mom=엄마 / mom_mid=엄마 얼굴 + 변화 후 전신 / mom_after=변화 후 얼굴·전신.
이미지는 shorts_cast_upload.labeled_refs(확정된 role 만, 칸 순서가 아니라 라벨 기준)에서 온다.
"""

from __future__ import annotations

from services import shorts_cast as sc
from services import shorts_cast_upload as up

MAX_REFS = 7
_ACTION_KEYS = {"dad": ("action",), "mom": ("action_front", "action_side"), "baby": ("action",)}


class CastNotReady(RuntimeError):
    """장면에 필요한 role 이 확정되지 않았거나 필수 이미지가 없다."""


def _need(refs: dict, role: str) -> dict:
    if not refs:
        raise CastNotReady(f"캐스트 '{role}' 가 확정되지 않았습니다 — /shorts/cast 에서 확정해 주세요.")
    return refs


def _first(refs: dict, *keys: str) -> str | None:
    for k in keys:
        if refs.get(k):
            return refs[k][0]
    return None


def role_candidates(channel: str, role: str, *, mom_stage: str = "mom", fmt: str = "B") -> dict:
    """{"primary": [face, front], "extra": [...], "bible": str} — 한 인물의 후보."""
    if role == "mom" and mom_stage in ("mom_mid", "mom_after"):
        after = _need(up.labeled_refs(channel, "mom_after"), "mom_after")
        base = _need(up.labeled_refs(channel, "mom"), "mom")
        face = _first(after if mom_stage == "mom_after" else base, "face")
        primary = [face, _first(after, "fullbody")]
        extra_src = base
        bible = sc.get_entry(channel, "mom_after")["bible"]
        if mom_stage == "mom_mid":
            bible += " — midway through the challenge: a little more toned than at the start"
    else:
        refs = _need(up.labeled_refs(channel, role), role)
        primary = [_first(refs, "face"), _first(refs, "front", "sheet:turnaround")]
        extra_src = refs
        bible = sc.get_entry(channel, role)["bible"]
    if fmt == "B":
        extra = [_first(extra_src, k) for k in _ACTION_KEYS.get(role, ())]
    elif fmt == "A":
        extra = [_first(extra_src, "expr", "sheet:expressions")]
    else:
        extra = []
    extra += [_first(extra_src, "threequarter", "side")]
    return {"primary": [u for u in primary if u], "extra": [u for u in extra if u], "bible": bible}


def select(channel: str, characters: list[str], *, mom_stage: str = "mom", fmt: str = "B",
           finale: bool = False) -> dict:
    """{"images": [...≤7], "bible": "외형 텍스트", "roles": [...]}. 미확정 role 이면 CastNotReady."""
    cands = [role_candidates(channel, r, mom_stage=mom_stage, fmt=fmt) for r in characters]
    images: list[str] = []

    def add(url: str | None) -> None:
        if url and url not in images and len(images) < MAX_REFS:
            images.append(url)

    for c in cands:
        for u in c["primary"]:
            add(u)
    bibles = [c["bible"] for c in cands]
    if len(characters) >= 2 or finale:
        fam = up.labeled_refs(channel, "family")
        group = (_first(fam, "finale") if finale else None) or _first(fam, "group")
        if not fam and len(characters) >= 2:
            raise CastNotReady("캐스트 'family' 가 확정되지 않았습니다 — /shorts/cast 에서 확정해 주세요.")
        add(group)
        if len(characters) >= 2:
            bibles.append("relative heights and proportions as in the family group reference")
    i = 0
    while len(images) < MAX_REFS and any(c["extra"] for c in cands):
        c = cands[i % len(cands)]
        if c["extra"]:
            add(c["extra"].pop(0))
        i += 1
    return {"images": images, "bible": "; ".join(bibles), "roles": list(characters)}
