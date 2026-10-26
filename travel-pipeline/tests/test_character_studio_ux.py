"""캐릭터 스튜디오 UX 단순화 — 얼굴 후보 다양화·전문가 프롬프트(참조 선택)·채널별 목록·쇼츠 가져오기(복사만)."""

from __future__ import annotations

import random
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import character_studio as cs  # noqa: E402
from services import character_studio_gen as gen  # noqa: E402
from services import character_studio_import as imp  # noqa: E402
from services import shorts_cast as sc  # noqa: E402
from test_character_studio import studio  # noqa: E402,F401
from test_character_studio_gen import _FakeMuse, _run, g  # noqa: E402,F401
from test_shorts_cast import env  # noqa: E402,F401


def _confirm(cid, role, url):
    ref = cs.insert_ref(cid, role, r2_key=f"characters/{cid}/{role}/x.png", url=url, source="upload")
    return cs.confirm_ref(ref["id"])


def test_face_variants_do_not_overlap():
    v = gen.face_variants(4, random.Random(1))
    assert len(set(v)) == 4
    eyes = [next(e for e in gen.FACE_EYES if e in line) for line in v]
    vibes = [next(x for x in gen.FACE_VIBES if x in line) for line in v]
    shapes = [next(x for x in gen.FACE_SHAPES if x in line) for line in v]
    assert len(set(eyes)) == 4 and len(set(vibes)) == 4 and len(set(shapes[:3])) == 3


def test_face_job_prompts_differ_and_stay_youthful(g):  # noqa: F811
    job = _run("chaei", [{"role": "01_face"}])
    prompts = [r["prompt"] for r in g.rest.tables[cs._REFS] if r["batch_id"] == job["id"]]
    assert len(prompts) == 4 and len(set(prompts)) == 4
    for p in prompts:
        assert "Youthful and fresh-faced" in p and "not resembling any real person or celebrity" in p
        assert "Distinct features for this candidate:" in p
    # 대표가 고친 프롬프트(고급 보기)는 그대로 — 변형 줄을 붙이지 않는다
    job = _run("chaei", [{"role": "01_face", "prompt": "my own face prompt", "count": 2}])
    assert {r["prompt"] for r in g.rest.tables[cs._REFS] if r["batch_id"] == job["id"]} == {"my own face prompt"}


def test_male_default_hair():
    assert "Short black hair" in gen.face_prompt({"subject_en": "man"})
    assert "Long straight black hair" in gen.face_prompt({"subject_en": "woman"})


def test_expert_prompt_with_chosen_refs(g):  # noqa: F811
    _confirm("chaei", "01_face", "https://img.test/face.png")
    _confirm("chaei", "hair_05_ponytail", "https://img.test/pony.png")
    char, refs = cs.get_character("chaei"), cs.confirmed_refs("chaei")
    p = gen.plan(char, "misc_look", refs, "custom prompt", ["hair_05_ponytail", "01_face"])
    assert p["references"] == ["https://img.test/pony.png", "https://img.test/face.png"] and p["kind"] == "custom"
    assert gen.plan(char, "misc_look", refs, "t2i only", [])["references"] == []
    with pytest.raises(cs.StudioError, match="확정되지 않은"):
        gen.plan(char, "misc_look", refs, "x", ["02_body"])
    job = _run("chaei", [{"role": "pose_custom", "prompt": "woman with fuller bust", "refs": ["01_face"], "count": 1}])
    assert job["done"] == 1 and g.muse.calls[-1].aspect_ratio == "9:16"
    with pytest.raises(cs.StudioError, match="형식"):
        gen.prepare_job("chaei", [{"role": "x_y", "prompt": "p", "refs": "01_face"}])


def test_overview_groups_by_channel(g):  # noqa: F811
    _confirm("chaei", "01_face", "https://img.test/face.png")
    cs.upsert_character("mina", "미나", channel_id="insta_chaei")
    cs.upsert_character("fit", "핏", channel_id="workout_music")
    _confirm("fit", "01_face", "https://img.test/fit.png")
    _confirm("fit", "02_body", "https://img.test/fitb.png")
    ov = {grp["channel_id"]: grp["characters"] for grp in imp.overview()}
    assert [c["id"] for c in ov["insta_chaei"]] == ["chaei", "mina"]
    chaei = ov["insta_chaei"][0]
    assert chaei["face_url"] == "https://img.test/face.png" and chaei["ready"] is False
    assert ov["insta_chaei"][1]["face_url"] is None and ov["workout_music"][0]["ready"] is True


@pytest.fixture
def shorts(g, monkeypatch):  # noqa: F811
    s3 = g.s3
    for aspect in ("face", "turnaround", "turnaround_p0"):
        s3.add(sc.aspect_key("workout_music", "hero", aspect), f"hero-{aspect}".encode())
    s3.add(sc.aspect_key("workout_music", "lead", sc.ANCHOR), b"lead-face")
    s3.copy_object = lambda Bucket, Key, CopySource, **kw: s3.add(Key, s3.objs[CopySource["Key"]][0])
    return g


def test_shorts_candidates_and_import_copies_only(shorts):
    before = {k: v[0] for k, v in shorts.s3.objs.items() if k.startswith("cast/")}
    cands = {c["role"]: c for c in imp.shorts_candidates()}
    assert set(cands) == {"hero", "lead"} and cands["hero"]["has_body"] and not cands["lead"]["has_body"]
    assert cands["hero"]["face_url"] == "https://img.test/cast/workout_music/hero/face.png"
    char = imp.import_shorts("workout_music", "hero")
    assert char["channel_id"] == "workout_music" and char["bible"]["source"] == "shorts"
    assert char["bible"]["subject_en"] == "man" and not char["bible"]["summary_en"].startswith("the hero")
    refs = cs.confirmed_refs(char["id"])
    assert set(refs) == {"01_face", "02_body"}
    assert shorts.s3.objs[refs["01_face"]["r2_key"]][0] == b"hero-face"
    assert shorts.s3.objs[refs["02_body"]["r2_key"]][0] == b"hero-turnaround"
    assert re.match(r"^characters/workout_hero/01_face/", refs["01_face"]["r2_key"])
    after = {k: v[0] for k, v in shorts.s3.objs.items() if k.startswith("cast/")}
    assert before == after                                                            # 원본 cast/… 무변경
    assert imp.import_shorts("workout_music", "hero")["id"] == char["id"]               # 두 번 눌러도 1명
    assert {c["role"]: c for c in imp.shorts_candidates()}["hero"]["imported_id"] == char["id"]
    with pytest.raises(cs.StudioNotFound):
        imp.import_shorts("workout_music", "dad")


def test_api_overview_and_import(shorts):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import studio as routes

    app = FastAPI()
    app.include_router(routes.router, prefix="/studio")
    c = TestClient(app)
    assert c.get("/studio/overview").status_code == 200
    assert len(c.get("/studio/shorts-cast").json()["cast"]) == 2
    r = c.post("/studio/import-shorts", json={"role": "lead"})
    assert r.status_code == 200 and r.json()["id"] == "workout_lead"
    assert c.post("/studio/import-shorts", json={"role": "baby"}).status_code == 404
    r = c.post("/studio/characters/chaei/generate", json={"items": [{"role": "misc_x", "prompt": "p", "refs": []}]})
    assert r.status_code == 200
