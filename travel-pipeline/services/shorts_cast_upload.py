"""쇼츠 캐스트 — 업로드 role(가족: dad·mom·mom_after·baby·family)의 슬롯 업로드·시트 자르기·라벨.

대표가 외부(메타 AI)에서 만든 이미지를 슬롯마다 올린다. 서버는:
1. ffprobe 로 해상도를 확인(얼굴 짧은 변 ≥768 / 그 외 긴 변 ≥1024)하고
2. ffmpeg 로 PNG 로 통일해 R2 cast/{channel}/{role}/{aspect}.png 에 저장한 뒤
3. 시트(strip=가로 N칸, grid=2×2)면 칸별로 잘라 {aspect}_p{i}.png 로 저장한다.

칸마다 대표가 라벨(정면/반측면/측면/뒤/사용안함, 표정 시트는 사용/사용안함)을 지정하고,
영상 레퍼런스 선택(2단계)은 칸 순서가 아니라 **이 라벨**을 기준으로 한다(labeled_refs).
"자르지 않기"(crop=False)면 원본 1장을 그대로 레퍼런스로 쓴다.

슬롯 메타(칸 수·자르기 여부·라벨)는 R2 JSON cast/{channel}/slots.json, 확정은 shorts_cast 의
state.json(role 단위)을 그대로 쓴다. 이미지·라벨이 바뀌면 그 role 의 확정을 푼다. SQL 없음.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from adapters import r2_storage
from services import shorts_cast as sc

logger = logging.getLogger(__name__)

MAX_BYTES = 15 * 1024 * 1024        # 서버 직접 호출 상한(프론트 경유는 Vercel 4.5MB 가 먼저 막힘)
MIN_FACE_SHORT = 768                # 얼굴: 짧은 변
MIN_OTHER_LONG = 1024               # 시트·전신·단체: 긴 변
ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}

TURN_LABELS = ("front", "threequarter", "side", "back", "unused")
EXPR_LABELS = ("expr", "unused")
LABEL_KO = {"front": "정면", "threequarter": "반측면", "side": "측면", "back": "뒤",
            "expr": "사용", "unused": "사용안함"}
_STRIP_COLS = (4, 5)


class UploadError(ValueError):
    """대표에게 그대로 보여줄 수 있는 업로드 오류(400)."""


# ── 슬롯 정의 ────────────────────────────────────────────────────────────
def upload_entries(channel: str) -> list[dict]:
    return [e for e in sc.HUMAN_CAST.get(channel, []) if e.get("source") == "upload"]


def get_slot(channel: str, role: str, aspect: str) -> dict:
    entry = sc.get_entry(channel, role)
    if not entry or entry.get("source") != "upload":
        raise UploadError(f"업로드 캐스트가 아닙니다: {role}")
    slot = next((s for s in entry["slots"] if s["key"] == aspect), None)
    if not slot:
        raise UploadError(f"알 수 없는 슬롯입니다: {role}/{aspect}")
    return slot


def default_labels(slot: dict, cols: int) -> list[str]:
    """칸 수별 기본 라벨 — 대표가 화면에서 바꾼다."""
    if slot["kind"] == "grid":
        return ["expr"] * 4
    base = ["front", "side", "back", "side", "unused"]
    return base[:cols]


def _panel_boxes(kind: str, cols: int, w: int, h: int) -> list[tuple[int, int, int, int]]:
    """(x, y, w, h) 칸 좌표. strip=가로 cols 등분, grid=2×2."""
    if kind == "grid":
        pw, ph = w // 2, h // 2
        return [(0, 0, pw, ph), (pw, 0, pw, ph), (0, ph, pw, ph), (pw, ph, pw, ph)]
    pw = w // cols
    return [(i * pw, 0, pw, h) for i in range(cols)]


# ── ffmpeg ───────────────────────────────────────────────────────────────
def probe(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0:s=x", str(path)],
        capture_output=True, text=True, timeout=30)
    try:
        w, h = (int(v) for v in out.stdout.strip().split("x")[:2])
    except ValueError:
        w = h = 0
    if out.returncode != 0 or w <= 0 or h <= 0:
        raise UploadError("이미지를 읽을 수 없어요 — png/jpg/webp 파일인지 확인해 주세요.")
    return w, h


def _ffmpeg(src: Path, dst: Path, vf: str | None = None) -> None:
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src)]
    if vf:
        cmd += ["-vf", vf]
    cmd += ["-frames:v", "1", str(dst)]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if res.returncode != 0 or not dst.exists():
        raise UploadError("이미지 변환에 실패했어요 — 다른 형식(png/jpg)으로 다시 올려 주세요.")


def check_resolution(slot: dict, w: int, h: int) -> None:
    if slot.get("min") == "face":
        if min(w, h) < MIN_FACE_SHORT:
            raise UploadError(f"얼굴 이미지가 작아요({w}×{h}). 짧은 변이 {MIN_FACE_SHORT}px 이상이어야 해요.")
    elif max(w, h) < MIN_OTHER_LONG:
        raise UploadError(f"이미지가 작아요({w}×{h}). 긴 변이 {MIN_OTHER_LONG}px 이상이어야 해요.")


# ── R2 ───────────────────────────────────────────────────────────────────
def _meta_key(channel: str) -> str:
    return f"cast/{channel}/slots.json"


def read_meta(channel: str) -> dict:
    """{role: {aspect: {cols, crop, labels, w, h, uploaded_at}}}. 없음/오류 → {}."""
    if not r2_storage.is_available():
        return {}
    try:
        obj = r2_storage._get_client().get_object(
            Bucket=r2_storage._character_bucket(), Key=_meta_key(channel))
        data = json.loads(obj["Body"].read())
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 - 없음 → 빈 메타
        return {}


def _write_meta(channel: str, meta: dict) -> None:
    r2_storage._get_client().put_object(
        Bucket=r2_storage._character_bucket(), Key=_meta_key(channel),
        Body=json.dumps(meta, ensure_ascii=False).encode(), ContentType="application/json")


def _panel_key(aspect: str, i: int) -> str:
    return f"{aspect}_p{i}"


def _put_png(path: Path, channel: str, role: str, name: str) -> None:
    r2_storage.upload_image(
        str(path), sc.aspect_key(channel, role, name),
        bucket=r2_storage._character_bucket(),
        public_base_url=r2_storage._character_public_base(),
        content_type="image/png",
    )


def _cut(png: Path, slot: dict, cols: int, w: int, h: int, channel: str, role: str, aspect: str,
         tmp: Path) -> int:
    boxes = _panel_boxes(slot["kind"], cols, w, h)
    for i, (x, y, pw, ph) in enumerate(boxes):
        out = tmp / f"p{i}.png"
        _ffmpeg(png, out, vf=f"crop={pw}:{ph}:{x}:{y}")
        _put_png(out, channel, role, _panel_key(aspect, i))
    return len(boxes)


# ── 업로드 / 다시 자르기 / 라벨 ──────────────────────────────────────────
def save_upload(channel: str, role: str, aspect: str, data: bytes, filename: str,
                cols: int | None = None) -> dict:
    """원본 저장(PNG 통일) + 시트면 칸 자르기(기본 라벨). 해당 role 확정 해제."""
    slot = get_slot(channel, role, aspect)
    if not r2_storage.is_available():
        raise RuntimeError("R2 미설정 — 업로드를 저장할 수 없습니다.")
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext not in ALLOWED_EXT:
        raise UploadError("png·jpg·webp 이미지만 올릴 수 있어요.")
    if len(data) > MAX_BYTES:
        raise UploadError(f"파일이 너무 커요({len(data) / 1e6:.1f}MB). 15MB 이하로 올려 주세요.")
    if not data:
        raise UploadError("빈 파일이에요.")
    cols = _valid_cols(slot, cols)
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        src = tmp / f"src.{ext}"
        src.write_bytes(data)
        w, h = probe(src)
        check_resolution(slot, w, h)
        png = tmp / "orig.png"
        _ffmpeg(src, png)
        _put_png(png, channel, role, aspect)
        entry = {"w": w, "h": h, "uploaded_at": datetime.now(timezone.utc).isoformat()}
        if slot["kind"] in ("strip", "grid"):
            _cut(png, slot, cols, w, h, channel, role, aspect, tmp)
            entry.update(cols=cols, crop=True, labels=default_labels(slot, cols))
    meta = read_meta(channel)
    meta.setdefault(role, {})[aspect] = entry
    _write_meta(channel, meta)
    sc._mark_draft(channel, role)
    return slot_view(channel, role, slot, meta, sc._list_objects(channel))


def _valid_cols(slot: dict, cols: int | None) -> int:
    if slot["kind"] == "grid":
        return 4
    if slot["kind"] != "strip":
        return 1
    cols = cols or slot.get("cols", 4)
    if cols not in _STRIP_COLS:
        raise UploadError("칸 수는 4 또는 5만 고를 수 있어요.")
    return cols


def update_slot(channel: str, role: str, aspect: str, *, cols: int | None = None,
                crop: bool | None = None, labels: list[str] | None = None) -> dict:
    """칸 수 변경(원본에서 다시 자르기)·자르지 않기 토글·칸별 라벨 지정. 해당 role 확정 해제."""
    slot = get_slot(channel, role, aspect)
    if slot["kind"] not in ("strip", "grid"):
        raise UploadError("시트 슬롯만 칸 설정을 바꿀 수 있어요.")
    meta = read_meta(channel)
    cur = (meta.get(role) or {}).get(aspect)
    if not cur:
        raise UploadError("먼저 이미지를 올려 주세요.")
    if cols is not None and slot["kind"] == "strip" and cols != cur.get("cols"):
        cols = _valid_cols(slot, cols)
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            png = tmp / "orig.png"
            r2_storage._get_client().download_file(
                r2_storage._character_bucket(), sc.aspect_key(channel, role, aspect), str(png))
            _cut(png, slot, cols, cur["w"], cur["h"], channel, role, aspect, tmp)
        cur.update(cols=cols, labels=default_labels(slot, cols))
    if crop is not None:
        cur["crop"] = bool(crop)
    if labels is not None:
        allowed = EXPR_LABELS if slot["kind"] == "grid" else TURN_LABELS
        if len(labels) != cur["cols"] or any(lb not in allowed for lb in labels):
            raise UploadError("칸 라벨이 올바르지 않아요.")
        cur["labels"] = list(labels)
    meta.setdefault(role, {})[aspect] = cur
    _write_meta(channel, meta)
    sc._mark_draft(channel, role)
    return slot_view(channel, role, slot, meta, sc._list_objects(channel))


# ── 조회 ─────────────────────────────────────────────────────────────────
def _url(channel: str, role: str, name: str, objects: dict[str, int]) -> str | None:
    k = sc.aspect_key(channel, role, name)
    return f"{sc._aspect_url(channel, role, name)}?v={objects[k]}" if k in objects else None


def slot_view(channel: str, role: str, slot: dict, meta: dict, objects: dict[str, int]) -> dict:
    m = (meta.get(role) or {}).get(slot["key"]) or {}
    view = {
        "key": slot["key"], "label": slot["label"], "kind": slot["kind"],
        "required": bool(slot.get("required")), "min": slot.get("min", "other"),
        "url": _url(channel, role, slot["key"], objects), "w": m.get("w"), "h": m.get("h"),
    }
    if slot["kind"] in ("strip", "grid"):
        cols = m.get("cols") or (4 if slot["kind"] == "grid" else slot.get("cols", 4))
        view.update(
            cols=cols, crop=m.get("crop", True),
            labels=m.get("labels") or default_labels(slot, cols),
            label_options=list(EXPR_LABELS if slot["kind"] == "grid" else TURN_LABELS),
            panels=[_url(channel, role, _panel_key(slot["key"], i), objects) for i in range(cols)]
            if m else [],
        )
    return view


def missing_required(channel: str, role: str, objects: dict[str, int] | None = None) -> list[str]:
    entry = sc.get_entry(channel, role) or {}
    objects = sc._list_objects(channel) if objects is None else objects
    return [s["label"] for s in entry.get("slots", [])
            if s.get("required") and sc.aspect_key(channel, role, s["key"]) not in objects]


def list_roles(channel: str) -> list[dict]:
    objects = sc._list_objects(channel)
    meta = read_meta(channel)
    state = sc.read_state(channel)
    return [{
        "role": e["role"], "label": e["label"], "summary": e["summary"],
        "active": e.get("active", True), "status": sc._status(state, e["role"]),
        "missing": missing_required(channel, e["role"], objects),
        "slots": [slot_view(channel, e["role"], s, meta, objects) for s in e["slots"]],
    } for e in upload_entries(channel)]


def approve(channel: str, role: str, approved: bool) -> dict:
    """role 단위 확정 — 필수 슬롯이 모두 있어야 확정 가능."""
    entry = sc.get_entry(channel, role)
    if not entry or entry.get("source") != "upload":
        raise UploadError(f"업로드 캐스트가 아닙니다: {role}")
    if approved:
        missing = missing_required(channel, role)
        if missing:
            raise UploadError("필수 이미지가 없어요: " + ", ".join(missing))
    return sc.set_status(channel, role, "approved" if approved else "draft")


def labeled_refs(channel: str, role: str) -> dict[str, list[str]]:
    """영상 레퍼런스용 — 확정된 role 의 이미지를 **라벨 기준**으로 묶는다(R2 공개 URL, ?v= 없음).

    {"face": [...], "front": [...], "threequarter": [...], "side": [...], "back": [...],
     "expr": [...], <단일 슬롯 key>: [...]}. 시트를 '자르지 않기'면 원본을 "sheet:<key>" 로.
    미확정·미업로드는 빈 dict.
    """
    if sc._status(sc.read_state(channel), role) != "approved":
        return {}
    entry = sc.get_entry(channel, role) or {}
    objects = sc._list_objects(channel)
    meta = read_meta(channel).get(role) or {}
    out: dict[str, list[str]] = {}
    for slot in entry.get("slots", []):
        key = slot["key"]
        if sc.aspect_key(channel, role, key) not in objects:
            continue
        if slot["kind"] == "single":
            out.setdefault(key, []).append(sc._aspect_url(channel, role, key))
            continue
        m = meta.get(key) or {}
        if not m.get("crop", True):
            out.setdefault(f"sheet:{key}", []).append(sc._aspect_url(channel, role, key))
            continue
        for i, label in enumerate(m.get("labels") or []):
            name = _panel_key(key, i)
            if label != "unused" and sc.aspect_key(channel, role, name) in objects:
                out.setdefault(label, []).append(sc._aspect_url(channel, role, name))
    return out
