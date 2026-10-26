"""캐릭터 스튜디오(A0-1) — 역할 규칙·업로드(실제 ffmpeg, R2·Supabase 모킹)·확정 교체·버리기·API."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import character_studio as cs  # noqa: E402
from test_shorts_cast import env  # noqa: E402,F401  (R2 모킹 fixture 재사용)

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 필요")


class _FakeRest:
    """_rest 대체 — 이 모듈이 쓰는 PostgREST 필터(eq/neq, order, on_conflict)만 흉내 낸다."""

    def __init__(self):
        self.tables: dict[str, list[dict]] = {cs._CHARS: [], cs._REFS: []}
        self.next_id = 1

    @staticmethod
    def _match(row: dict, params: dict) -> bool:
        for k, v in params.items():
            if k in ("select", "order", "on_conflict"):
                continue
            op, _, val = v.partition(".")
            cur = "" if row.get(k) is None else str(row.get(k))
            if (op == "eq" and cur != val) or (op == "neq" and cur == val):
                return False
        return True

    def __call__(self, method, table, *, params=None, json=None, prefer=None):
        params = params or {}
        rows = self.tables[table]
        if method == "GET":
            return [dict(r) for r in rows if self._match(r, params)]
        if method == "POST":
            out = []
            for rec in json:
                if params.get("on_conflict") == "id":
                    old = next((r for r in rows if r["id"] == rec["id"]), None)
                    if old:
                        old.update(rec)
                        out.append(dict(old))
                        continue
                    rec = {"bible": {}, "channel_id": None, **rec}
                else:
                    rec = {**rec, "id": self.next_id, "confirmed_at": None}
                    self.next_id += 1
                rows.append(dict(rec))
                out.append(dict(rec))
            return out
        if method == "PATCH":
            hit = [r for r in rows if self._match(r, params)]
            for r in hit:
                r.update(json)
            # 부분 유니크 인덱스 흉내: 역할마다 confirmed 최대 1장
            seen = set()
            for r in rows:
                if table == cs._REFS and r["status"] == "confirmed":
                    k = (r["character_id"], r["role"])
                    assert k not in seen, f"confirmed 중복: {k}"
                    seen.add(k)
            return [dict(r) for r in hit]
        raise AssertionError(method)


@pytest.fixture
def studio(env, monkeypatch):  # noqa: F811
    fake = _FakeRest()
    monkeypatch.setattr(cs, "_rest", fake)
    cs.upsert_character("chaei", "채이", channel_id="insta_chaei", bible={"age": 24})
    env.rest = fake
    return env


def _img(tmp_path: Path, w: int, h: int, ext: str = "png") -> bytes:
    out = tmp_path / f"in_{w}x{h}.{ext}"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=gray:s={w}x{h}",
                    "-frames:v", "1", str(out)], check=True)
    return out.read_bytes()


def test_role_rules():
    assert cs.check_role("hair_01_straight") == "hair_01_straight"
    for bad in ("", "A_face", "hair-01", "x", "a" * 41, "../x"):
        with pytest.raises(cs.StudioError):
            cs.check_role(bad)
    assert [cs.role_category(r) for r in ("01_face", "02_body", "hair_11_headband", "pose_walk", "misc")] == \
        ["face", "body", "hair", "pose", "other"]
    with pytest.raises(cs.StudioError):
        cs.check_character_id("Chaei")


@needs_ffmpeg
def test_import_upload_confirms_and_stores_png(studio, tmp_path):
    ref = cs.save_upload("chaei", "01_face", _img(tmp_path, 900, 1200, "webp"), "01_face.webp")
    assert ref["status"] == "confirmed" and ref["source"] == "upload" and (ref["w"], ref["h"]) == (900, 1200)
    assert ref["r2_key"].startswith("characters/chaei/01_face/") and ref["r2_key"].endswith(".png")
    assert ref["url"] == f"https://img.test/{ref['r2_key']}"
    assert studio.s3.objs[ref["r2_key"]][0][:8] == b"\x89PNG\r\n\x1a\n"     # PNG 로 통일
    assert not any(k.startswith("cast/") for k in studio.s3.objs)              # hero·백곰 키 무관


@needs_ffmpeg
def test_resolution_and_format_errors(studio, tmp_path):
    with pytest.raises(cs.StudioError, match="짧은 변이 768"):
        cs.save_upload("chaei", "01_face", _img(tmp_path, 700, 1400), "f.png")
    with pytest.raises(cs.StudioError, match="긴 변이 1024"):
        cs.save_upload("chaei", "hair_01_straight", _img(tmp_path, 900, 900), "h.png")
    with pytest.raises(cs.StudioError, match="png·jpg·webp"):
        cs.save_upload("chaei", "01_face", b"GIF89a", "x.gif")
    with pytest.raises(cs.StudioNotFound):
        cs.save_upload("nobody", "01_face", b"x", "x.png")
    assert studio.rest.tables[cs._REFS] == []


@needs_ffmpeg
def test_confirm_swaps_and_discard(studio, tmp_path):
    img = _img(tmp_path, 1024, 1536)
    a = cs.save_upload("chaei", "02_body", img, "a.png")
    b = cs.save_upload("chaei", "02_body", img, "b.png", confirm=False)
    assert b["status"] == "candidate" and cs.confirmed_refs("chaei")["02_body"]["id"] == a["id"]
    cs.confirm_ref(b["id"])
    assert cs.confirmed_refs("chaei")["02_body"]["id"] == b["id"]
    assert cs.get_ref(a["id"])["status"] == "candidate"                         # 이전 확정은 후보로
    cs.discard_ref(a["id"])
    view = cs.character_view("chaei")
    body = next(s for s in view["roles"] if s["role"] == "02_body")
    assert body["confirmed"]["id"] == b["id"] and body["candidates"] == []      # 버린 건 숨김
    assert view["missing_required"] == ["01_face"] and view["ready"] is False
    cs.save_upload("chaei", "01_face", _img(tmp_path, 1024, 1024), "f.png")
    assert cs.character_view("chaei")["ready"] is True


def test_upsert_keeps_existing_fields(studio):
    cs.upsert_character("chaei", "채이2")
    ch = cs.get_character("chaei")
    assert ch["name"] == "채이2" and ch["channel_id"] == "insta_chaei" and ch["bible"] == {"age": 24}


@needs_ffmpeg
def test_api_routes(studio, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import studio as routes

    app = FastAPI()
    app.include_router(routes.router, prefix="/studio")
    c = TestClient(app)
    assert c.get("/studio/roles").json()["required"] == ["01_face", "02_body"]
    assert [x["id"] for x in c.get("/studio/characters").json()["characters"]] == ["chaei"]
    r = c.post("/studio/characters/chaei/upload", data={"role": "hair_01_straight"},
               files={"file": ("h.png", _img(tmp_path, 1024, 1536), "image/png")})
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    assert c.post("/studio/characters/chaei/upload", data={"role": "BAD"},
                  files={"file": ("h.png", b"x", "image/png")}).status_code == 400
    assert c.get("/studio/characters/nobody").status_code == 404
    assert c.post("/studio/refs/999/confirm").status_code == 404
    rid = r.json()["id"]
    assert c.post(f"/studio/refs/{rid}/discard").json()["status"] == "discarded"
