"""쇼츠 사람 캐스트 시트 — 생성·재생성·확정·R2 키·프롬프트(외부 API 실호출 없음)."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import shorts_cast as sc  # noqa: E402
from test_workout_image_reuse import _FakeS3  # noqa: E402

CH, ROLE = "workout_music", "lead"


class _Adapter:
    def __init__(self, fail=()):
        self.calls: list = []
        self.fail = set(fail)

    def is_available(self):
        return True

    async def generate(self, req):
        self.calls.append(req)
        key = Path(req.output_path).stem
        if key in self.fail:
            raise RuntimeError("boom")
        Path(req.output_path).write_bytes(b"PNG")
        return SimpleNamespace(source_url=f"https://cdn/{key}.png")


@pytest.fixture
def env(monkeypatch, tmp_path):
    s3 = _FakeS3()
    from adapters import r2_storage
    monkeypatch.setattr(r2_storage, "is_available", lambda: True)
    monkeypatch.setattr(r2_storage, "_get_client", lambda: s3)
    monkeypatch.setattr(r2_storage, "_character_bucket", lambda: "chars")
    monkeypatch.setattr(r2_storage, "_character_public_base", lambda: "https://img.test")

    def upload(path, key, **kw):
        assert kw["bucket"] == "chars"
        s3.add(key, Path(path).read_bytes())
        return f"https://img.test/{key}"
    monkeypatch.setattr(r2_storage, "upload_image", upload)
    t2i, kontext = _Adapter(), _Adapter()
    monkeypatch.setattr(sc, "get_image_adapter", lambda: t2i)
    monkeypatch.setattr(sc, "get_kontext_adapter", lambda: kontext)
    monkeypatch.chdir(tmp_path)
    sc._PROGRESS.clear()
    return SimpleNamespace(s3=s3, t2i=t2i, kontext=kontext)


def test_aspects_cover_the_order():
    assert sc.ASPECT_KEYS == ["front", "threequarter", "side", "workout_full", "casual_full",
                              "selfie_bust", "expr_smile", "expr_determined"]
    assert sc.ASPECT_LABELS["workout_full"] == "운동복 전신" and sc.ASPECT_LABELS["casual_full"] == "일상복 전신"


def test_bible_and_prompts_are_human_original_without_names():
    e = sc.get_entry(CH, ROLE)
    core = e["core"]
    assert "East Asian man in his early twenties" in core and "not bulky" in core and "black hair" in core
    for key in sc.ASPECT_KEYS:
        p, ratio = sc._aspect_prompt(core, key)
        assert "ORIGINAL fictional person" in p and "not resembling" in p and "anime" in p
        assert "Photorealistic" in p and "No text" in p
        assert not re.search(r"\b(mascot|fur|animal|bear)\b", p, re.I)    # 백곰 동물 문구 없음
        assert ratio == ("1:1" if key.startswith("expr_") else "9:16")
    assert "Waist-up FRONT" in sc.front_prompt(core)
    assert "hoodie" in sc._aspect_prompt(core, "casual_full")[0]
    assert "training shorts" in sc._aspect_prompt(core, "workout_full")[0]
    assert "selfie" in sc._aspect_prompt(core, "selfie_bust")[0]
    assert "label" in e and "name" not in e                               # 이름 필드 없음(메타 미사용)


def test_generate_all_front_then_refs_and_r2_keys(env):
    sc.run_generation(CH, ROLE)
    prog = sc.get_progress(CH, ROLE)
    assert prog["status"] == "done" and prog["generated"] == sc.ASPECT_KEYS and prog["total"] == 8
    assert len(env.t2i.calls) == 1 and env.t2i.calls[0].reference_images is None
    assert len(env.kontext.calls) == 7
    assert all(c.reference_images and c.reference_images[0].endswith("front.png") for c in env.kontext.calls)
    keys = {k for k in env.s3.objs if k.endswith(".png")}
    assert keys == {f"cast/workout_music/lead/{a}.png" for a in sc.ASPECT_KEYS}
    assert not any(k.startswith("cast/lead/") or k.startswith("cast/protagonist") for k in env.s3.objs)
    cast = sc.list_cast(CH)
    assert cast[0]["status"] == "draft" and set(cast[0]["aspects"]) == set(sc.ASPECT_KEYS)
    assert cast[0]["aspects"]["front"].startswith("https://img.test/cast/workout_music/lead/front.png?v=")


def test_partial_failure_and_front_failure(env):
    env.kontext.fail = {"side"}
    sc.run_generation(CH, ROLE)
    p = sc.get_progress(CH, ROLE)
    assert p["status"] == "done" and p["failed"] == ["side"] and "side" not in p["generated"]
    env.t2i.fail = {"front"}
    sc.run_generation(CH, ROLE)
    p = sc.get_progress(CH, ROLE)
    assert p["status"] == "failed" and p["failed"] == sc.ASPECT_KEYS


def test_approve_and_regenerate_resets_to_draft(env):
    sc.run_generation(CH, ROLE)
    assert sc.reference_urls(CH, ROLE) == []                              # 미확정 → 레퍼런스 없음
    sc.set_status(CH, ROLE, "approved")
    assert sc.list_cast(CH)[0]["status"] == "approved"
    assert sc.reference_urls(CH, ROLE) == ["https://img.test/cast/workout_music/lead/front.png",
                                           "https://img.test/cast/workout_music/lead/threequarter.png"]
    out = sc.regenerate_aspect(CH, ROLE, "selfie_bust")
    assert out["url"].startswith("https://img.test/cast/workout_music/lead/selfie_bust.png?v=")
    assert "warning" not in out
    assert env.kontext.calls[-1].reference_images == ["https://img.test/cast/workout_music/lead/front.png"]
    assert sc.list_cast(CH)[0]["status"] == "draft"                        # 바뀌면 다시 승인
    out = sc.regenerate_aspect(CH, ROLE, "front")
    assert "warning" in out and len(env.t2i.calls) == 2


def test_regenerate_requires_front_and_valid_aspect(env):
    with pytest.raises(RuntimeError):
        sc.regenerate_aspect(CH, ROLE, "side")
    with pytest.raises(ValueError):
        sc.regenerate_aspect(CH, ROLE, "expr_sad")
    with pytest.raises(ValueError):
        sc.regenerate_aspect(CH, "nobody", "side")
    with pytest.raises(ValueError):
        sc.set_status(CH, ROLE, "weird")


def test_routes(env):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes import shorts
    app = FastAPI()
    app.include_router(shorts.router, prefix="/shorts")
    c = TestClient(app)
    r = c.get("/shorts/cast?channel=workout_music").json()
    assert [a["key"] for a in r["aspects"]] == sc.ASPECT_KEYS and r["cast"][0]["role"] == "lead"
    assert c.get("/shorts/cast?channel=sayeon").status_code == 404
    assert c.post("/shorts/cast/generate", json={"channel": CH, "role": ROLE}).json()["status"] == "running"
    assert c.get("/shorts/cast/status").json()["status"] == "done"            # TestClient 는 백그라운드를 끝까지 실행
    assert c.post("/shorts/cast/approve", json={"approved": True}).json()["status"] == "approved"
    assert c.post("/shorts/cast/aspect", json={"aspect": "bad"}).status_code == 400
    assert c.post("/shorts/cast/aspect", json={"aspect": "side"}).json()["aspect"] == "side"
    sc._set(CH, ROLE, status="running")
    assert c.post("/shorts/cast/generate", json={}).status_code == 409
