"""캐릭터 스튜디오(채널 공통) — 캐릭터와 역할별 기준 이미지 등록·조회·확정 (A0-1).

채이(인스타 쇼핑)를 시작으로, 이후 모든 캐릭터가 같은 저장소를 쓴다.
- 역할(role)은 코드 상수가 아니라 데이터다: '01_face', '02_body', 'hair_01_straight', 'pose_walk' …
  이름 규칙(_ROLE_RE)만 지키면 자유롭게 늘린다. 분류(face/body/hair/pose/other)는 접두사로 정한다.
- 이미지: ffmpeg 로 PNG 통일 → R2 캐릭터 버킷 characters/{character_id}/{role}/{시각}_{난수}.png.
  올릴 때마다 새 키라 덮어쓰기·캐시버스팅이 없다. 버린 이미지도 R2 에서 바로 지우지 않는다.
- 상태: Supabase studio_characters / studio_character_refs (docs/studio_characters.sql).
  역할마다 confirmed 는 최대 1장(부분 유니크 인덱스). 새로 확정하면 이전 확정은 candidate 로 내려가
  다시 고를 수 있다.

쇼츠 hero(cast/{channel}/…, R2 JSON)·백곰(cast/{role}/…, sayeon_cast)은 건드리지 않는다.
shorts_cast_upload 의 ffprobe/ffmpeg 헬퍼만 import 해서 쓴다.
"""

from __future__ import annotations

import logging
import re
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

from adapters import r2_storage
from services import shorts_cast_upload as up
from services.music_store import _http_err, _supabase_cfg

logger = logging.getLogger(__name__)

_CHARS = "studio_characters"
_REFS = "studio_character_refs"
_SELECT_REF = "id,character_id,role,status,source,r2_key,url,w,h,prompt,parent_ref_id,batch_id,created_at,confirmed_at"

MAX_BYTES = up.MAX_BYTES
ALLOWED_EXT = up.ALLOWED_EXT

_CHAR_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
_ROLE_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,39}$")

# 분류 — 접두사로 판정. min: 해상도 규칙(face=짧은 변 768↑, 그 외 긴 변 1024↑, shorts_cast_upload 와 동일).
CATEGORIES: list[dict] = [
    {"key": "face", "label": "얼굴", "match": re.compile(r"^\d{2}_face$|^face(_|$)"), "min": "face"},
    {"key": "body", "label": "체형 시트", "match": re.compile(r"^\d{2}_body$|^body(_|$)"), "min": "other"},
    {"key": "hair", "label": "헤어", "match": re.compile(r"^hair_"), "min": "other"},
    {"key": "pose", "label": "포즈", "match": re.compile(r"^pose_"), "min": "other"},
]
REQUIRED_ROLES = ("01_face", "02_body")  # 착장 생성 때 매번 넣는 기준 2장


class StudioError(ValueError):
    """대표에게 그대로 보여줄 수 있는 입력 오류(400)."""


class StudioNotFound(LookupError):
    """캐릭터·이미지 없음(404)."""


class StudioStoreError(RuntimeError):
    """Supabase·R2 저장 실패(502)."""


# ── 규칙 ─────────────────────────────────────────────────────────────────
def check_character_id(character_id: str) -> str:
    cid = (character_id or "").strip()
    if not _CHAR_ID_RE.match(cid):
        raise StudioError("캐릭터 ID 는 영문 소문자로 시작하는 2~32자(소문자·숫자·_)여야 해요.")
    return cid


def check_role(role: str) -> str:
    r = (role or "").strip()
    if not _ROLE_RE.match(r):
        raise StudioError("역할 이름은 소문자·숫자·_ 2~40자여야 해요(예: 01_face, hair_01_straight).")
    return r


def role_category(role: str) -> str:
    for c in CATEGORIES:
        if c["match"].search(role):
            return c["key"]
    return "other"


def _min_rule(role: str) -> str:
    cat = role_category(role)
    return next((c["min"] for c in CATEGORIES if c["key"] == cat), "other")


# ── Supabase(PostgREST) ──────────────────────────────────────────────────
def _rest(method: str, table: str, *, params: dict | None = None, json: object = None,
          prefer: str | None = None) -> list[dict]:
    """PostgREST 1회 호출 → 행 목록. 미설정·오류는 StudioStoreError."""
    url, key = _supabase_cfg()
    if not (url and key):
        raise StudioStoreError("Supabase 미설정 — 캐릭터 스튜디오를 쓸 수 없습니다.")
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.request(method, f"{url}/rest/v1/{table}", headers=headers, params=params, json=json)
            r.raise_for_status()
            data = r.json() if r.content else []
    except Exception as e:  # noqa: BLE001
        msg = _http_err(e)
        logger.warning("[studio] %s %s 실패: %s", method, table, msg)
        raise StudioStoreError(f"저장소 오류: {msg}") from e
    return data if isinstance(data, list) else []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 캐릭터 ───────────────────────────────────────────────────────────────
def list_characters() -> list[dict]:
    return _rest("GET", _CHARS, params={"select": "*", "order": "created_at.asc"})


def get_character(character_id: str) -> dict:
    cid = check_character_id(character_id)
    rows = _rest("GET", _CHARS, params={"select": "*", "id": f"eq.{cid}"})
    if not rows:
        raise StudioNotFound(f"캐릭터가 없어요: {cid}")
    return rows[0]


def upsert_character(character_id: str, name: str, *, channel_id: str | None = None,
                     bible: dict | None = None) -> dict:
    """캐릭터 생성·수정(id 기준). 주지 않은 channel_id·bible 은 기존 값을 유지한다."""
    cid = check_character_id(character_id)
    name = (name or "").strip()
    if not name:
        raise StudioError("캐릭터 이름을 입력해 주세요.")
    row: dict = {"id": cid, "name": name[:40], "updated_at": _now()}
    if channel_id is not None:
        row["channel_id"] = channel_id.strip() or None
    if bible is not None:
        if not isinstance(bible, dict):
            raise StudioError("bible 은 객체(JSON)여야 해요.")
        row["bible"] = bible
    rows = _rest("POST", _CHARS, params={"on_conflict": "id"}, json=[row],
                 prefer="resolution=merge-duplicates,return=representation")
    return rows[0] if rows else row


# ── 기준 이미지 ──────────────────────────────────────────────────────────
def list_refs(character_id: str, *, include_discarded: bool = False) -> list[dict]:
    cid = check_character_id(character_id)
    params = {"select": _SELECT_REF, "character_id": f"eq.{cid}", "order": "role.asc,created_at.desc"}
    if not include_discarded:
        params["status"] = "neq.discarded"
    return _rest("GET", _REFS, params=params)


def get_ref(ref_id: int) -> dict:
    rows = _rest("GET", _REFS, params={"select": _SELECT_REF, "id": f"eq.{int(ref_id)}"})
    if not rows:
        raise StudioNotFound(f"이미지가 없어요: {ref_id}")
    return rows[0]


def confirmed_refs(character_id: str) -> dict[str, dict]:
    """{role: ref} — 확정된 기준 이미지만. 착장 생성(A1)이 여기서 face·body·헤어를 고른다."""
    cid = check_character_id(character_id)
    rows = _rest("GET", _REFS, params={"select": _SELECT_REF, "character_id": f"eq.{cid}",
                                       "status": "eq.confirmed"})
    return {r["role"]: r for r in rows}


def character_view(character_id: str) -> dict:
    """화면용: 캐릭터 + 역할별 {confirmed, candidates} + 필수 역할 충족 여부."""
    char = get_character(character_id)
    roles: dict[str, dict] = {}
    for r in list_refs(char["id"]):
        slot = roles.setdefault(r["role"], {"role": r["role"], "category": role_category(r["role"]),
                                            "confirmed": None, "candidates": []})
        if r["status"] == "confirmed":
            slot["confirmed"] = r
        else:
            slot["candidates"].append(r)
    missing = [r for r in REQUIRED_ROLES if not (roles.get(r) or {}).get("confirmed")]
    return {
        "character": char,
        "roles": sorted(roles.values(), key=lambda s: s["role"]),
        "required": list(REQUIRED_ROLES),
        "missing_required": missing,
        "ready": not missing,
    }


def _r2_key(character_id: str, role: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"characters/{character_id}/{role}/{stamp}_{secrets.token_hex(3)}.png"


def insert_ref(character_id: str, role: str, *, r2_key: str, url: str, source: str,
               w: int | None = None, h: int | None = None, prompt: str | None = None,
               parent_ref_id: int | None = None, batch_id: str | None = None) -> dict:
    """R2 에 이미 올라간 이미지를 candidate 로 등록. 생성 흐름(A0-3)도 이 함수를 쓴다."""
    cid = check_character_id(character_id)
    role = check_role(role)
    if source not in ("upload", "generated"):
        raise StudioError(f"알 수 없는 source: {source}")
    row = {"character_id": cid, "role": role, "status": "candidate", "source": source,
           "r2_key": r2_key, "url": url, "w": w, "h": h, "prompt": prompt,
           "parent_ref_id": parent_ref_id, "batch_id": batch_id}
    rows = _rest("POST", _REFS, json=[row], prefer="return=representation")
    if not rows:
        raise StudioStoreError("이미지 등록 응답이 비었어요.")
    return rows[0]


def save_upload(character_id: str, role: str, data: bytes, filename: str, *,
                confirm: bool = True) -> dict:
    """업로드 1장 → PNG 통일 → R2 → 등록. confirm=True(기본, 기존 이미지 가져오기)면 바로 확정."""
    char = get_character(character_id)
    role = check_role(role)
    ext = (filename.rsplit(".", 1)[-1] if "." in (filename or "") else "").lower()
    if ext not in ALLOWED_EXT:
        raise StudioError("png·jpg·webp 이미지만 올릴 수 있어요.")
    if not data:
        raise StudioError("빈 파일이에요.")
    if len(data) > MAX_BYTES:
        raise StudioError(f"파일이 너무 커요({len(data) / 1e6:.1f}MB). 15MB 이하로 올려 주세요.")
    if not r2_storage.is_available():
        raise StudioStoreError("R2 미설정 — 업로드를 저장할 수 없습니다.")
    key = _r2_key(char["id"], role)
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        src = tmp / f"src.{ext}"
        src.write_bytes(data)
        try:
            w, h = up.probe(src)
            up.check_resolution({"min": _min_rule(role)}, w, h)
            png = tmp / "ref.png"
            up._ffmpeg(src, png)
        except up.UploadError as e:
            raise StudioError(str(e)) from e
        try:
            url = r2_storage.upload_image(
                str(png), key,
                bucket=r2_storage._character_bucket(),
                public_base_url=r2_storage._character_public_base(),
                content_type="image/png",
            )
        except Exception as e:  # noqa: BLE001
            raise StudioStoreError(str(e)) from e
    ref = insert_ref(char["id"], role, r2_key=key, url=url, source="upload", w=w, h=h)
    logger.info("[studio] 업로드 %s/%s → ref %s", char["id"], role, ref.get("id"))
    return confirm_ref(ref["id"]) if confirm else ref


def confirm_ref(ref_id: int) -> dict:
    """이 이미지를 그 역할의 확정으로. 같은 역할의 이전 확정은 candidate 로 내린다."""
    ref = get_ref(ref_id)
    if ref["status"] == "confirmed":
        return ref
    _rest("PATCH", _REFS,
          params={"character_id": f"eq.{ref['character_id']}", "role": f"eq.{ref['role']}",
                  "status": "eq.confirmed"},
          json={"status": "candidate", "confirmed_at": None}, prefer="return=minimal")
    rows = _rest("PATCH", _REFS, params={"id": f"eq.{ref['id']}"},
                 json={"status": "confirmed", "confirmed_at": _now()}, prefer="return=representation")
    return rows[0] if rows else {**ref, "status": "confirmed"}


def discard_ref(ref_id: int) -> dict:
    """버리기(목록에서 숨김). R2 파일은 남긴다(되돌릴 수 있게)."""
    ref = get_ref(ref_id)
    rows = _rest("PATCH", _REFS, params={"id": f"eq.{ref['id']}"},
                 json={"status": "discarded", "confirmed_at": None}, prefer="return=representation")
    return rows[0] if rows else {**ref, "status": "discarded"}


def role_presets() -> dict:
    """화면용 역할 안내 — 분류·필수 역할·이름 규칙."""
    return {
        "categories": [{"key": c["key"], "label": c["label"], "min": c["min"]} for c in CATEGORIES]
        + [{"key": "other", "label": "기타", "min": "other"}],
        "required": list(REQUIRED_ROLES),
        "pattern": _ROLE_RE.pattern,
        "examples": ["01_face", "02_body", "hair_01_straight", "hair_11_headband", "pose_walk"],
    }
