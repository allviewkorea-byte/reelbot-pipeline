"""포즈 라이브러리(2026-10-30) — 목록 파싱·설정·선택·프롬프트 연결. 외부 호출 없이 모킹."""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import insta_outfit as io  # noqa: E402
from services import insta_outfit_plan as P  # noqa: E402
from services import insta_pose_lib as pl  # noqa: E402

POSES = [
    {"key": "全身1人・標準系|P001", "id": "P001", "s": 1, "cat": "站立", "zh": "站姿", "ja": "",
     "angles": {"正面": "full_std_P001_front", "斜45°": "full_std_P001_diag", "俯视": "full_std_P001_high"}},
    {"key": "全身1人・標準系|P002", "id": "P002", "s": 1, "cat": "坐姿", "zh": "坐姿", "ja": "",
     "angles": {"正面": "full_std_P002_front"}},
    {"key": "全身1人・セクシー系|P001", "id": "P001", "s": 0, "cat": "性感·露骨系", "zh": "x", "ja": "",
     "angles": {"正面": "full_sexy_P001_front"}},
]


@pytest.fixture(autouse=True)
def store(monkeypatch):
    box: dict = {}
    monkeypatch.setattr(pl, "_r2_get", lambda k: json.loads(json.dumps(box[k])) if k in box else None)
    monkeypatch.setattr(pl, "_r2_put", lambda k, d: box.__setitem__(k, d) or True)
    pl._CACHE.clear()
    pl._CACHE["poses"] = POSES
    pl._CACHE["i18n"] = {"全身1人・標準系|P001": {"ko": "기본 서기", "en": "standing with weight on one leg"}}
    monkeypatch.setattr(pl, "ensure_i18n_async", lambda: None)
    return box


def test_parse_drops_thumbnails():
    js = 'window.LIB_POSE=' + json.dumps({"data": {"series": [], "poses": [
        {"key": "k", "s": 1, "id": "P1", "cat": "站立", "zh": "z", "ja": "j", "ang": {"正面": "b_front"}},
        {"key": "k2", "s": 1, "id": "P2", "cat": "站立", "zh": "z", "ang": {}}]}, "img": {"b_front": "data:..."}}) + ";"
    got = pl.parse_catalog(js)
    assert got == [{"key": "k", "id": "P1", "s": 1, "cat": "站立", "zh": "z", "ja": "j", "angles": {"正面": "b_front"}}]


def test_real_repo_file_if_present():
    f = Path("/tmp/claude-0/-home-claude/fb1e3644-330d-5abe-949c-46ccd1731ae0/scratchpad/refrepo/ai-ref-library-cn/data/pose.js")
    if not f.exists():
        pytest.skip("깃허브 사본 없음")
    got = pl.parse_catalog(f.read_text())
    assert len(got) == 288 and all(p["cat"] in pl.CAT_KO for p in got)
    assert all(k.split("|")[1] in pl.CAT_KO for k in pl.DEFAULT_CATS)


def test_default_off_and_settings_roundtrip():
    assert pl.get_settings()["enabled"] is False
    assert pl.pick(rng=random.Random(1)) is None
    s = pl.save_settings({"enabled": True, "cats": ["0|性感·露骨系"], "angles": ["正面", "bogus"]})
    assert s["enabled"] and s["cats"] == ["0|性感·露骨系"] and s["angles"] == ["正面"]
    assert pl.pick(rng=random.Random(1))["key"] == "全身1人・セクシー系|P001"   # 대표가 켠 카테고리는 그대로 쓴다


def test_pick_respects_cats_angles_excluded_recent():
    st = {"enabled": True, "cats": ["1|站立", "1|坐姿"], "angles": ["斜45°"], "excluded": []}
    p = pl.pick(rng=random.Random(0), settings=st)
    assert p["key"] == "全身1人・標準系|P001" and p["angle"] == "斜45°"            # P002 는 45° 없음
    assert p["url"] == "https://ai-pose-gallery.pages.dev/img/full_std_P001_diag.png" and p["en"].startswith("standing")
    st2 = {**st, "angles": ["正面"]}
    keys = {pl.pick(rng=random.Random(i), settings=st2, recent=["全身1人・標準系|P001"])["key"] for i in range(20)}
    assert keys == {"全身1人・標準系|P002"}
    assert pl.pick(settings={**st2, "excluded": ["全身1人・標準系|P001", "全身1人・標準系|P002"]}) is None


def test_listing_counts_and_korean():
    d = pl.listing()
    cats = {c["key"]: c for c in d["categories"]}
    assert cats["1|站立"]["ko"] == "서기" and cats["1|站立"]["enabled"] and not cats["0|性感·露骨系"]["enabled"]
    first = next(p for p in d["poses"] if p["id"] == "P001" and p["series"] == 1)
    assert first["ko"] == "기본 서기" and first["angles"][0]["url"].endswith(".png")
    assert "giaaibusi" in d["credit"]


def _plan():
    loc = next(k for k, v in P.LOCATIONS.items() if v["kind"] not in ("room", "entry"))
    pose = next(k for k, v in P.POSES.items() if v.get("person") is not False and v.get("feet") != "socks")
    return {"location": loc, "pose": pose, "season": "autumn"}


def test_build_inserts_pose_ref_before_products():
    prods = [{"kind": "top", "url": "https://x/p1.png"}, {"kind": "bottoms", "url": "https://x/p2.png"}]
    plan = _plan()
    prompt, refs = P.build(plan, face_url="F", body_url="B", hair_url="H", products=prods,
                           pose_ref={"url": "https://pose/a.png", "en": "standing tall"})
    assert refs[:4] == ["F", "B", "H", "https://pose/a.png"] and refs[4:] == ["https://x/p1.png", "https://x/p2.png"]
    assert "reference image 4 (standing tall)" in prompt and "image 5" in prompt
    assert P.POSES[plan["pose"]]["en"] not in prompt
    plain, refs2 = P.build(plan, face_url="F", body_url="B", hair_url="H", products=prods)
    assert "mannequin" not in plain and len(refs2) == 5


def test_run_helpers(monkeypatch, tmp_path):
    plan = _plan()
    monkeypatch.setattr(pl, "pick", lambda **k: {"key": "K", "id": "P1", "cat_ko": "서기", "angle": "正面",
                                                  "ko": "서기", "url": "https://pose/a.png", "en": ""})
    monkeypatch.setattr(pl, "download", lambda pose, dest, http=None: str(dest))
    pose, local = io._pick_pose(plan, [{"plan": {"pose_ref": {"key": "OLD"}}}], tmp_path, None)
    assert pose["key"] == "K" and local.endswith("pose_ref.png") and plan["pose_ref"]["key"] == "K"
    assert io._local_pose(["F", "https://pose/a.png", "P"], pose, local) == ["F", local, "P"]
    monkeypatch.setattr(pl, "download", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("404")))
    assert io._pick_pose(_plan(), [], tmp_path, None) == (None, None)    # 실패해도 생성은 계속


def test_i18n_batches(store):
    calls = []

    def llm(system, user):
        keys = json.loads(user)
        calls.append(len(keys))
        return json.dumps({k: {"ko": "한글", "en": "eng"} for k in keys})
    got = pl.build_i18n(POSES, llm=llm, batch=1)
    assert calls == [1, 1] and got["全身1人・セクシー系|P001"]["ko"] == "한글" and pl.I18N_KEY in store
