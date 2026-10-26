"""캐릭터 스튜디오 — 채널별 캐릭터 목록(얼굴 썸네일·준비 상태) + 쇼츠 캐스트 가져오기(복사만).

- overview(): 스튜디오 캐릭터를 channel_id 로 묶어 얼굴 썸네일·준비 상태와 함께 돌려준다(첫 화면).
- 쇼츠 가져오기: 운동 채널 쇼츠 캐스트(R2 cast/{channel}/{role}/{aspect}.png, shorts_cast)의 얼굴·체형
  이미지를 스튜디오 저장소(characters/{id}/{role}/…)로 **복사**해 새 캐릭터로 등록한다.
  원본 cast/… 와 쇼츠 확정 상태(state.json·slots.json)는 읽기만 하고 절대 바꾸지 않는다. 쇼츠 제작 코드 무변경.
"""

from __future__ import annotations

import logging
import re

from adapters import r2_storage
from services import character_studio as cs
from services import shorts_cast as sc

logger = logging.getLogger(__name__)

# 쇼츠 아스펙트 → 스튜디오 역할(앞에 있는 것부터 첫 번째로 존재하는 것을 쓴다)
FACE_ASPECTS = ("face", sc.ANCHOR)
BODY_ASPECTS = ("turnaround", "fullbody", "daily_full", "workout_full")


def overview() -> list[dict]:
    """[{channel_id, characters: [{id, name, face_url, ready, source}]}] — 채널 순서는 첫 등장 순."""
    chars = cs.list_characters()
    rows = cs._rest("GET", cs._REFS, params={
        "select": "character_id,role,url", "status": "eq.confirmed",
        "role": f"in.({cs.REQUIRED_ROLES[0]},{cs.REQUIRED_ROLES[1]})"})
    have: dict[str, dict[str, str]] = {}
    for r in rows:
        have.setdefault(r["character_id"], {})[r["role"]] = r["url"]
    groups: dict[str, list[dict]] = {}
    for c in chars:
        got = have.get(c["id"], {})
        groups.setdefault(c.get("channel_id") or "", []).append({
            "id": c["id"], "name": c["name"], "face_url": got.get(cs.REQUIRED_ROLES[0]),
            "ready": all(r in got for r in cs.REQUIRED_ROLES),
            "source": ((c.get("bible") or {}).get("source") or "studio"),
            "shorts_role": (c.get("bible") or {}).get("shorts_role"),
        })
    return [{"channel_id": k, "characters": v} for k, v in groups.items()]


def _first(keys: dict[str, int], channel: str, role: str, aspects: tuple[str, ...]) -> str | None:
    return next((sc.aspect_key(channel, role, a) for a in aspects if sc.aspect_key(channel, role, a) in keys), None)


def shorts_candidates(channel: str = "workout_music") -> list[dict]:
    """가져올 수 있는 쇼츠 캐스트 = 얼굴 이미지가 R2 에 있는 역할. 이미 가져온 건 imported_id 표시."""
    keys = sc._list_objects(channel)
    base = r2_storage._character_public_base().rstrip("/")
    imported = {((c.get("bible") or {}).get("shorts_role"), c.get("channel_id")): c["id"]
                for c in cs.list_characters() if (c.get("bible") or {}).get("source") == "shorts"}
    out = []
    for entry in sc.HUMAN_CAST.get(channel, []):
        role = entry["role"]
        face = _first(keys, channel, role, FACE_ASPECTS)
        if not face:
            continue
        body = _first(keys, channel, role, BODY_ASPECTS)
        name = entry.get("subtitle_name") or entry.get("label") or role
        out.append({"role": role, "name": name, "label": entry.get("label") or role,
                    "face_url": f"{base}/{face}", "has_body": bool(body),
                    "imported_id": imported.get((role, channel))})
    return out


def _new_id(channel: str, role: str) -> str:
    base = re.sub(r"[^a-z0-9_]", "", f"{channel.split('_')[0]}_{role}".lower())[:28] or "shorts_char"
    if not re.match(r"^[a-z]", base):
        base = f"s_{base}"
    taken = {c["id"] for c in cs.list_characters()}
    cid, n = base, 2
    while cid in taken:
        cid, n = f"{base}_{n}", n + 1
    return cs.check_character_id(cid)


def import_shorts(channel: str, role: str) -> dict:
    """쇼츠 캐스트 1명 → 스튜디오 캐릭터(얼굴·체형 복사 + 확정). 이미 가져왔으면 그 캐릭터를 돌려준다."""
    cand = next((c for c in shorts_candidates(channel) if c["role"] == role), None)
    if not cand:
        raise cs.StudioNotFound("쇼츠에서 가져올 수 있는 캐릭터가 아니에요(얼굴 이미지 없음).")
    if cand["imported_id"]:
        return cs.get_character(cand["imported_id"])
    if not r2_storage.is_available():
        raise cs.StudioStoreError("R2 미설정 — 가져올 수 없어요.")
    keys = sc._list_objects(channel)
    pairs = [(cs.REQUIRED_ROLES[0], _first(keys, channel, role, FACE_ASPECTS)),
             (cs.REQUIRED_ROLES[1], _first(keys, channel, role, BODY_ASPECTS))]
    cid = _new_id(channel, role)
    entry = next(e for e in sc.HUMAN_CAST[channel] if e["role"] == role)
    desc = re.sub(r"^the [^:]{1,40}:\s*", "", str(entry.get("core") or entry.get("bible") or ""))
    bible = {"source": "shorts", "shorts_role": role, "summary_en": desc[:300],
             "subject_en": "woman" if re.search(r"\bwoman\b", desc) else "man" if re.search(r"\bman\b", desc) else None}
    char = cs.upsert_character(cid, cand["name"], channel_id=channel, bible={k: v for k, v in bible.items() if v})
    client, bucket = r2_storage._get_client(), r2_storage._character_bucket()
    base = r2_storage._character_public_base().rstrip("/")
    for studio_role, src in pairs:
        if not src:
            continue
        dst = cs._r2_key(cid, studio_role)
        try:  # 같은 버킷 안 서버 측 복사 — 원본(cast/…)은 그대로
            client.copy_object(Bucket=bucket, Key=dst, CopySource={"Bucket": bucket, "Key": src},
                               ContentType="image/png", MetadataDirective="REPLACE")
        except Exception as e:  # noqa: BLE001
            raise cs.StudioStoreError(f"이미지 복사 실패({src}): {e}") from e
        ref = cs.insert_ref(cid, studio_role, r2_key=dst, url=f"{base}/{dst}", source="upload")
        cs.confirm_ref(ref["id"])
    logger.info("[studio] 쇼츠 %s/%s → 스튜디오 %s 가져오기", channel, role, cid)
    return char
