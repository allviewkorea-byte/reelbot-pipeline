"""쇼츠 가족 캐스트 업로드 — 형식 변환·해상도·시트 자르기·라벨·확정·레퍼런스(실제 ffmpeg, R2 모킹)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import shorts_cast as sc  # noqa: E402
from services import shorts_cast_upload as up  # noqa: E402
from test_shorts_cast import env  # noqa: E402,F401  (R2·어댑터 모킹 fixture 재사용)

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 필요")
CH = "workout_music"


def _img(tmp_path: Path, w: int, h: int, ext: str) -> bytes:
    out = tmp_path / f"in_{w}x{h}.{ext}"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=red:s={w}x{h}",
                    "-frames:v", "1", str(out)], check=True)
    return out.read_bytes()


def _png_size(s3, key: str, tmp_path: Path) -> tuple[int, int]:
    p = tmp_path / "chk.png"
    p.write_bytes(s3.objs[key][0])
    assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"                      # PNG 로 통일
    return up.probe(p)


@pytest.fixture
def real_upload(env, monkeypatch):  # noqa: F811
    """upload_image 를 파일 내용 그대로 저장하도록(env 의 fake 는 이미 그렇게 동작)."""
    return env


@pytest.mark.parametrize("ext", ["webp", "png", "jpg"])
def test_single_upload_each_format(real_upload, tmp_path, ext):
    view = up.save_upload(CH, "dad", "face", _img(tmp_path, 900, 1200, ext), f"a.{ext}")
    assert view["url"].startswith("https://img.test/cast/workout_music/dad/face.png?v=")
    assert _png_size(real_upload.s3, "cast/workout_music/dad/face.png", tmp_path) == (900, 1200)
    assert view["w"] == 900 and view["h"] == 1200


def test_resolution_and_format_errors(real_upload, tmp_path):
    with pytest.raises(up.UploadError, match="짧은 변이 768"):
        up.save_upload(CH, "mom", "face", _img(tmp_path, 700, 1400, "png"), "f.png")
    with pytest.raises(up.UploadError, match="긴 변이 1024"):
        up.save_upload(CH, "family", "group", _img(tmp_path, 1000, 800, "png"), "g.png")
    with pytest.raises(up.UploadError, match="png·jpg·webp"):
        up.save_upload(CH, "mom", "face", b"GIF89a", "x.gif")
    with pytest.raises(up.UploadError, match="15MB"):
        up.save_upload(CH, "mom", "face", b"0" * (up.MAX_BYTES + 1), "x.png")
    with pytest.raises(up.UploadError, match="읽을 수 없어요"):
        up.save_upload(CH, "mom", "face", b"not an image", "x.png")
    with pytest.raises(up.UploadError, match="알 수 없는 슬롯"):
        up.save_upload(CH, "mom", "nope", _img(tmp_path, 900, 900, "png"), "x.png")
    with pytest.raises(up.UploadError, match="업로드 캐스트가 아닙니다"):
        up.save_upload(CH, "lead", "glow_front", _img(tmp_path, 900, 900, "png"), "x.png")


def test_strip_cut_cols_and_labels(real_upload, tmp_path):
    s3 = real_upload.s3
    # 아기 턴어라운드 = 기본 5칸
    view = up.save_upload(CH, "baby", "turnaround", _img(tmp_path, 2000, 900, "webp"), "t.webp")
    assert view["cols"] == 5 and view["crop"] is True and len(view["panels"]) == 5
    assert view["labels"] == ["front", "side", "back", "side", "unused"]
    assert _png_size(s3, "cast/workout_music/baby/turnaround_p4.png", tmp_path) == (400, 900)
    # 엄마 턴어라운드: 기본 4칸 → 가운데 두 칸 모두 측면으로 라벨 지정
    up.save_upload(CH, "mom", "turnaround", _img(tmp_path, 2000, 900, "jpg"), "t.jpg")
    assert _png_size(s3, "cast/workout_music/mom/turnaround_p0.png", tmp_path) == (500, 900)
    view = up.update_slot(CH, "mom", "turnaround", labels=["front", "side", "side", "back"])
    assert view["labels"] == ["front", "side", "side", "back"]
    # 칸 수 4 → 5 로 바꾸면 원본에서 다시 자르고 라벨은 기본값
    view = up.update_slot(CH, "mom", "turnaround", cols=5)
    assert view["cols"] == 5 and len(view["panels"]) == 5 and view["labels"][-1] == "unused"
    assert _png_size(s3, "cast/workout_music/mom/turnaround_p4.png", tmp_path) == (400, 900)
    with pytest.raises(up.UploadError, match="4 또는 5"):
        up.update_slot(CH, "mom", "turnaround", cols=3)
    with pytest.raises(up.UploadError, match="라벨"):
        up.update_slot(CH, "mom", "turnaround", labels=["front", "top", "side", "back", "unused"])
    with pytest.raises(up.UploadError, match="라벨"):
        up.update_slot(CH, "mom", "turnaround", labels=["front"])
    with pytest.raises(up.UploadError, match="시트 슬롯만"):
        up.update_slot(CH, "mom", "face", crop=False)


def test_grid_cut(real_upload, tmp_path):
    view = up.save_upload(CH, "dad", "expressions", _img(tmp_path, 1200, 1200, "png"), "e.png")
    assert view["cols"] == 4 and view["labels"] == ["expr"] * 4 and view["label_options"] == ["expr", "unused"]
    assert _png_size(real_upload.s3, "cast/workout_music/dad/expressions_p3.png", tmp_path) == (600, 600)


def _fill_required(tmp_path, role):
    sizes = {"face": (900, 1200), "turnaround": (2000, 900), "fullbody": (800, 1400), "group": (1400, 1000)}
    for slot in sc.get_entry(CH, role)["slots"]:
        if slot.get("required"):
            w, h = sizes[slot["key"]]
            up.save_upload(CH, role, slot["key"], _img(tmp_path, w, h, "png"), "x.png")


def test_approve_requires_slots_and_upload_resets(real_upload, tmp_path):
    with pytest.raises(up.UploadError, match="필수 이미지가 없어요: 기준 얼굴, 전신 4방향"):
        up.approve(CH, "mom", True)
    _fill_required(tmp_path, "mom")
    up.approve(CH, "mom", True)
    roles = {r["role"]: r for r in up.list_roles(CH)}
    assert roles["mom"]["status"] == "approved" and roles["mom"]["missing"] == []
    assert roles["dad"]["status"] == "draft" and "기준 얼굴" in roles["dad"]["missing"]
    # 교체·라벨 변경은 그 role 확정만 푼다
    up.update_slot(CH, "mom", "turnaround", labels=["front", "side", "side", "back"])
    assert {r["role"]: r for r in up.list_roles(CH)}["mom"]["status"] == "draft"
    up.approve(CH, "mom", True)
    up.save_upload(CH, "mom", "action_front", _img(tmp_path, 900, 1400, "png"), "a.png")
    assert {r["role"]: r for r in up.list_roles(CH)}["mom"]["status"] == "draft"
    # family.finale 는 선택 — group 만 있으면 확정
    _fill_required(tmp_path, "family")
    up.approve(CH, "family", True)


def test_labeled_refs_follow_labels_not_order(real_upload, tmp_path):
    _fill_required(tmp_path, "mom")
    up.update_slot(CH, "mom", "turnaround", labels=["front", "side", "side", "back"])
    assert up.labeled_refs(CH, "mom") == {}                                # 미확정 → 없음
    up.approve(CH, "mom", True)
    base = "https://img.test/cast/workout_music/mom/"
    refs = up.labeled_refs(CH, "mom")
    assert refs["face"] == [base + "face.png"]
    assert refs["front"] == [base + "turnaround_p0.png"]
    assert refs["side"] == [base + "turnaround_p1.png", base + "turnaround_p2.png"]
    assert refs["back"] == [base + "turnaround_p3.png"] and "threequarter" not in refs
    # 라벨을 바꾸면 순서와 무관하게 라벨대로 + 사용안함 제외
    up.update_slot(CH, "mom", "turnaround", labels=["back", "unused", "threequarter", "front"])
    up.approve(CH, "mom", True)
    refs = up.labeled_refs(CH, "mom")
    assert refs["front"] == [base + "turnaround_p3.png"] and refs["back"] == [base + "turnaround_p0.png"]
    assert refs["threequarter"] == [base + "turnaround_p2.png"] and "side" not in refs
    # 자르지 않기 → 원본 시트 1장
    up.update_slot(CH, "mom", "turnaround", crop=False)
    up.approve(CH, "mom", True)
    refs = up.labeled_refs(CH, "mom")
    assert refs["sheet:turnaround"] == [base + "turnaround.png"] and "front" not in refs


def test_lead_archived_and_routes(real_upload, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes import shorts
    app = FastAPI()
    app.include_router(shorts.router, prefix="/shorts")
    c = TestClient(app)
    r = c.get("/shorts/cast").json()
    assert r["cast"][0]["role"] == "lead" and r["cast"][0]["active"] is False      # 서준호 보관
    assert [x["role"] for x in r["roles"]] == ["hero", "dad", "mom", "mom_after", "baby", "family"]
    assert [x["active"] for x in r["roles"]] == [True, False, False, False, False, False]   # 2026-10-21 단독 주인공
    fam = r["roles"][-1]
    assert [s["key"] for s in fam["slots"]] == ["group", "finale"] and fam["slots"][1]["required"] is False
    assert c.post("/shorts/cast/generate", json={"role": "mom"}).status_code == 400   # 업로드 role 생성 불가
    res = c.post("/shorts/cast/upload", data={"role": "baby", "aspect": "turnaround", "cols": "5"},
                 files={"file": ("t.webp", _img(tmp_path, 2000, 900, "webp"), "image/webp")})
    assert res.status_code == 200 and res.json()["cols"] == 5
    res = c.post("/shorts/cast/upload", data={"role": "baby", "aspect": "face"},
                 files={"file": ("f.png", _img(tmp_path, 500, 500, "png"), "image/png")})
    assert res.status_code == 400 and "768" in res.json()["detail"]
    assert c.post("/shorts/cast/approve", json={"role": "baby", "approved": True}).status_code == 400
    res = c.post("/shorts/cast/slot", json={"role": "baby", "aspect": "turnaround",
                                            "labels": ["front", "threequarter", "side", "back", "unused"]})
    assert res.status_code == 200 and res.json()["labels"][1] == "threequarter"
    meta = json.loads(real_upload.s3.objs["cast/workout_music/slots.json"][0])
    assert meta["baby"]["turnaround"]["labels"][1] == "threequarter"


def test_hero_role_slots():
    """2026-10-21: 210cm 단독 주인공(hero) — 필수=기준 얼굴·상의 탈의 4방향·운동복 4방향, 가족은 보관."""
    from services import shorts_cast as sc
    hero = sc.get_entry(CH, "hero")
    assert hero["source"] == "upload" and hero["active"] is True and "210 cm" in hero["bible"]
    req = [s["key"] for s in hero["slots"] if s.get("required")]
    assert req == ["face", "turnaround_shirtless", "turnaround"]
    assert all(not sc.get_entry(CH, r)["active"] for r in ("dad", "mom", "mom_after", "baby", "family"))
