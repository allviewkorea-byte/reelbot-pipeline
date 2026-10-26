"""캐릭터 스튜디오 생성(A0-3) — Muse 페이로드·프롬프트 템플릿·안전 재시도·잡·bible·역할 추천·API.

실호출 없음: Muse 어댑터·Claude 는 가짜. R2·Supabase 는 test_character_studio 의 fixture 재사용.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.base import ImageGenerationRequest, ImageGenerationResult  # noqa: E402
from adapters.image.muse_adapter import EDIT_MODEL, T2I_MODEL, MuseImageAdapter  # noqa: E402
from adapters.video.wavespeed_ref_video_adapter import RefBlocked  # noqa: E402
from services import character_studio as cs  # noqa: E402
from services import character_studio_gen as gen  # noqa: E402
from test_character_studio import studio  # noqa: E402,F401
from test_shorts_cast import env  # noqa: E402,F401


class _FakeMuse:
    """요청을 기록하고 1×1 PNG 를 쓴다. block: 프롬프트에 이 문자열이 있으면 RefBlocked."""

    def __init__(self):
        self.calls: list[ImageGenerationRequest] = []
        self.block: str | None = None
        self.always_block = False

    def is_available(self):
        return True

    async def generate(self, req):
        self.calls.append(req)
        if self.always_block or (self.block and self.block in req.prompt):
            raise RefBlocked("content policy violation: sensitive")
        Path(req.output_path).write_bytes(b"\x89PNG\r\n\x1a\nfake")
        return ImageGenerationResult(image_path=req.output_path, cost_usd=0.011, model_used="muse", raw_response={})


@pytest.fixture
def g(studio, monkeypatch):  # noqa: F811
    muse = _FakeMuse()
    monkeypatch.setattr(gen, "get_muse_adapter", lambda: muse)
    gen._JOBS.clear()
    cs.upsert_character("chaei", "채이", bible={"subject_en": "woman", "age": 24, "height_cm": 172,
                                               "summary_en": "24-year-old Korean woman, an office worker living in Seoul",
                                               "hair_en": "long straight black hair"})
    studio.muse = muse
    return studio


def _run(character_id, items, **kw):
    job = gen.prepare_job(character_id, items, **kw)
    gen.run_job(job["id"])
    return gen.get_job(job["id"])


def _confirm(role, url="https://img.test/x.png"):
    ref = cs.insert_ref("chaei", role, r2_key=f"characters/chaei/{role}/x.png", url=url, source="upload")
    return cs.confirm_ref(ref["id"])


def test_muse_payload_t2i_and_edit():
    m, p = MuseImageAdapter.build(ImageGenerationRequest(prompt="p", aspect_ratio="3:4"))
    assert m == T2I_MODEL and p["aspect_ratio"] == "3:4" and p["output_format"] == "png" and "image_urls" not in p
    refs = [f"https://img.test/{i}.png" for i in range(12)]
    m, p = MuseImageAdapter.build(ImageGenerationRequest(prompt="p", reference_images=refs, aspect_ratio="7:3"))
    assert m == EDIT_MODEL and p["image_urls"] == refs[:10] and p["aspect_ratio"] == "3:4"   # 최대 10장, 이상한 비율 → 3:4


def test_templates_use_verified_text():
    b = {"subject_en": "woman", "height_cm": 172, "summary_en": "24-year-old Korean woman", "hair_en": "long straight black hair"}
    assert gen.face_prompt(b).startswith("Original fictional 24-year-old Korean woman, not resembling any real person")
    assert "plain light gray background" in gen.face_prompt(b)
    body = gen.body_prompt(b)
    assert "172cm tall model proportions" in body and "light grey fitted ribbed tank top" in body
    assert "Change only the hairstyle: long hair in a sleek high ponytail." in gen.hair_prompt(b, gen.HAIR_PRESETS[4]["line"])
    for p in gen.POSE_PRESETS:
        line = p["line"]
        assert "face is not visible" in line or "covering her face" in line
        if "sneakers" in line or "loafers" in line:                      # 신발 보이면 실내(거실·방) 금지
            assert not any(w in line for w in ("living room", "bedroom"))
    for text in [gen.face_prompt(b), body, *(gen.hair_prompt(b, h["line"]) for h in gen.HAIR_PRESETS)]:
        assert not any(w in text.lower() for w in ("bust", "cropped at the neck", "chest"))


def test_sanitize():
    assert gen.sanitize("woman with fuller bust, cropped at the neck") == \
        "woman with, framed from the shoulders down so her face is not visible"
    assert gen.sanitize("plain prompt").endswith(gen._SAFE_SUFFIX)          # 바뀐 게 없으면 안전 문구 추가


def test_presets_roles_and_save(g):
    pr = gen.presets(cs.get_character("chaei"))
    assert [h["role"] for h in pr["hair"]][:2] == ["hair_01_straight", "hair_02_wave"]
    assert pr["hair"][-1]["role"] == "hair_11_headband" and len(pr["hair"]) == 11
    new = [*({"key": h["key"], "line": h["line"]} for h in gen.HAIR_PRESETS[1:]), {"key": "bob", "line": "short chin-length bob"}]
    out = gen.save_presets("chaei", "hair", new)
    assert out["hair"][0]["role"] == "hair_01_wave" and out["hair"][-1]["role"] == "hair_11_bob"
    assert cs.get_character("chaei")["bible"]["age"] == 24                  # bible 다른 값 유지
    with pytest.raises(cs.StudioError):
        gen.save_presets("chaei", "hair", [{"key": "Bad Key", "line": "xxxxx"}])


def test_plan_requires_references(g):
    char = cs.get_character("chaei")
    assert gen.plan(char, "01_face", {})["references"] == []
    with pytest.raises(cs.StudioError, match="얼굴"):
        gen.plan(char, "02_body", {})
    face = _confirm("01_face", "https://img.test/face.png")
    refs = cs.confirmed_refs("chaei")
    p = gen.plan(char, "hair_05_ponytail", refs)
    assert p["references"] == ["https://img.test/face.png"] and p["parent_ref_id"] == face["id"] and p["aspect"] == "3:4"
    with pytest.raises(cs.StudioError, match="체형"):
        gen.plan(char, "pose_walk", refs)
    _confirm("02_body", "https://img.test/body.png")
    p = gen.plan(char, "pose_walk", cs.confirmed_refs("chaei"))
    assert p["references"] == ["https://img.test/face.png", "https://img.test/body.png"] and p["aspect"] == "9:16"
    assert gen.plan(char, "hair_05_ponytail", refs, prompt="custom")["prompt"] == "custom"   # 고급 보기


def test_job_creates_candidates(g):
    job = _run("chaei", [{"role": "01_face"}])
    assert job["state"] == "done" and job["total"] == 4 and job["done"] == 4 and job["cost_usd"] == 0.044
    rows = [r for r in g.rest.tables[cs._REFS] if r["role"] == "01_face"]
    assert len(rows) == 4 and all(r["status"] == "candidate" and r["source"] == "generated" for r in rows)
    assert all(r["batch_id"] == job["id"] and r["prompt"].startswith("Original fictional") for r in rows)
    assert all(c.reference_images is None and c.aspect_ratio == "3:4" for c in g.muse.calls)
    assert all(r["r2_key"].startswith("characters/chaei/01_face/") for r in rows)

    face = cs.confirm_ref(rows[0]["id"])
    job = _run("chaei", [{"role": "02_body"}, {"role": "hair_01_straight"}, {"role": "hair_07_cap"}])
    assert job["total"] == 6 and job["done"] == 6
    new = [r for r in g.rest.tables[cs._REFS] if r["batch_id"] == job["id"]]
    assert {r["role"] for r in new} == {"02_body", "hair_01_straight", "hair_07_cap"}
    assert all(r["parent_ref_id"] == face["id"] for r in new)
    assert all(c.reference_images == [face["url"]] for c in g.muse.calls[4:])


def test_safety_retry_then_fail(g):
    _confirm("01_face")
    g.muse.block = "bust"
    job = _run("chaei", [{"role": "hair_01_straight", "prompt": "woman with fuller bust, long hair", "count": 1}])
    assert job["done"] == 1 and job["failed"] == 0                          # 표현 바꿔 1회 재시도로 통과
    assert "bust" not in g.rest.tables[cs._REFS][-1]["prompt"]
    g.muse.always_block = True
    job = _run("chaei", [{"role": "hair_01_straight", "count": 1}])
    assert job["state"] == "failed" and job["failed"] == 1 and "안전 필터" in job["errors"][0]
    assert len(g.muse.calls) == 2 + 2                                       # 성공 건 2회 + 실패 건 2회(재시도 1회)


def test_prepare_validation(g):
    with pytest.raises(cs.StudioError):
        gen.prepare_job("chaei", [])
    with pytest.raises(cs.StudioError, match="1~6"):
        gen.prepare_job("chaei", [{"role": "01_face", "count": 9}])
    with pytest.raises(cs.StudioError, match="자동 생성할 수 없는"):
        gen.prepare_job("chaei", [{"role": "misc_thing"}])


def test_create_character_with_ai_bible(g, monkeypatch):
    from services import music_lyrics
    monkeypatch.setattr(music_lyrics, "_call", lambda *a, **k: (
        '```json\n{"id": "chaei", "subject_en": "woman", "age": 24, "height_cm": 172, '
        '"summary_en": "24-year-old Korean woman with a curvy figure", "hair_en": "long black hair", '
        '"vibe_en": "minimal", "notes_ko": "서울 직장인"}\n```'))
    char = gen.create_character("채이", "서울 사는 24살 직장인, 긴 흑발, 172cm")
    assert char["id"] == "chaei_2"                                          # 이미 있는 id → 접미사
    assert "curvy" not in char["bible"]["summary_en"] and char["bible"]["description_ko"].startswith("서울")


def test_suggest_parse():
    pr = gen.presets({"bible": {}})
    p = lambda t: gen._parse_suggest(t, pr["hair"], pr["pose"])  # noqa: E731
    assert p('{"kind":"face","role":"x","confidence":0.9,"reason":"얼굴"}')["role"] == "01_face"
    assert p('{"kind":"body","confidence":2}') == {"kind": "body", "role": "02_body", "confidence": 1.0, "reason": ""}
    assert p('{"kind":"hair","role":"ponytail"}')["role"] == "hair_05_ponytail"
    assert p('{"kind":"hair","role":"hair_08_beanie"}')["role"] == "hair_08_beanie"
    assert p('{"kind":"weird","role":"01_face"}')["kind"] == "not_reference"
    # 착장·라이프스타일 컷이 pose 로 와도 목록에 없는 역할이면 기준 이미지 아님(기본 제외)
    assert p('{"kind":"pose","role":"pose_xxx","reason":"착장"}') == \
        {"kind": "not_reference", "role": "", "confidence": 0.0, "reason": "착장"}
    assert p('{"kind":"pose","role":""}')["kind"] == "not_reference"
    assert p('{"kind":"pose","role":"pose_walk"}')["role"] == "pose_walk"
    sysmsg = gen._suggest_system(pr["hair"], pr["pose"])
    assert "pose_walk" in sysmsg and "hair_02_wave" in sysmsg and "outfit" in sysmsg and "ignore any file name" in sysmsg


def test_suggest_role_calls_vision(g, monkeypatch, tmp_path):
    """route → 서비스 → Claude 비전 호출 → 파싱까지(가짜 클라이언트). 실패는 502 + 사유."""
    import subprocess
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import studio as routes
    from services import music_lyrics

    sent = {}

    class _Msgs:
        def create(self, **kw):
            sent.update(kw)
            if sent.get("fail"):
                raise RuntimeError("boom")
            return SimpleNamespace(content=[SimpleNamespace(text='{"kind":"hair","role":"hair_02_wave","confidence":0.8,"reason":"웨이브"}')],
                                   usage=None)

    class _Client:
        messages = _Msgs()

        def with_options(self, **kw):
            return self

    monkeypatch.setattr(music_lyrics, "_client", lambda: _Client())
    img = tmp_path / "hair_02_straight.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=1024x1536",
                    "-frames:v", "1", str(img)], check=True)
    app = FastAPI()
    app.include_router(routes.router, prefix="/studio")
    c = TestClient(app)
    r = c.post("/studio/characters/chaei/suggest-role", files={"file": (img.name, img.read_bytes(), "image/png")})
    assert r.status_code == 200 and r.json()["role"] == "hair_02_wave" and r.json()["kind"] == "hair"
    assert sent["messages"][0]["content"][0]["type"] == "image" and "hair_11_headband" in sent["system"]
    sent["fail"] = True
    from services import music_llm_fallback as fb
    monkeypatch.setattr(fb, "enabled", lambda: False)
    r = c.post("/studio/characters/chaei/suggest-role", files={"file": (img.name, img.read_bytes(), "image/png")})
    assert r.status_code == 502 and "AI 역할 추천 실패" in r.json()["detail"]


def test_api_generate_and_job(g):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import studio as routes

    app = FastAPI()
    app.include_router(routes.router, prefix="/studio")
    c = TestClient(app)
    view = c.get("/studio/characters/chaei").json()
    assert len(view["presets"]["hair"]) == 11 and view["presets"]["pose"][0]["role"] == "pose_stand"
    r = c.post("/studio/characters/chaei/generate", json={"items": [{"role": "01_face", "count": 2}]})
    assert r.status_code == 200 and r.json()["est_usd"] == 0.022 and "plans" not in r.json()
    assert c.get(f"/studio/jobs/{r.json()['id']}").json()["state"] == "done"   # TestClient 는 백그라운드를 응답 뒤 실행
    assert c.post("/studio/characters/chaei/generate", json={"items": [{"role": "02_body"}]}).status_code == 400
    assert c.get("/studio/jobs/nope").status_code == 404
    assert c.get("/studio/characters/chaei/plan", params={"role": "01_face"}).json()["prompt"].startswith("Original")


def test_api_create_starts_face_job(g, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import studio as routes
    from services import music_lyrics

    monkeypatch.setattr(music_lyrics, "_call", lambda *a, **k: '{"id": "mina", "subject_en": "woman", "age": 27}')
    app = FastAPI()
    app.include_router(routes.router, prefix="/studio")
    c = TestClient(app)
    r = c.post("/studio/create", json={"name": "미나", "description": "서울 사는 27살 디자이너"})
    assert r.status_code == 200 and r.json()["character"]["id"] == "mina" and r.json()["job"]["total"] == 4
    faces = [x for x in g.rest.tables[cs._REFS] if x["character_id"] == "mina" and x["role"] == "01_face"]
    assert len(faces) == 4
    assert c.post("/studio/create", json={"name": "", "description": "x"}).status_code == 400
