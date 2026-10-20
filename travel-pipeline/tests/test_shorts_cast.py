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
    assert sc.ASPECT_KEYS == ["front", "daily_threequarter", "daily_full", "office_full",
                              "glow_front", "glow_side", "workout_full", "gym_shirtless"]
    assert sc.ASPECT_LABELS["front"].startswith("평소 정면") and sc.ASPECT_LABELS["gym_shirtless"] == "체육관 상의 탈의 상반신"
    # 평소 컷·반전 정면은 평소 정면, 나머지 반전 컷은 반전 정면을 레퍼런스로
    assert [sc.aspect_base(k) for k in sc.ASPECT_KEYS] == [
        None, "front", "front", "front", "front", "glow_front", "glow_front", "glow_front"]


def test_bible_and_prompts_are_original_without_name():
    e = sc.get_entry(CH, ROLE)
    core = e["core"]
    assert "25-year-old East Asian man" in core and e["subtitle_name"] == "서준호"
    for key in sc.ASPECT_KEYS:
        p, ratio = sc._aspect_prompt(core, key)
        assert "ORIGINAL fictional person" in p and "not resembling" in p and "anime" in p
        assert "Photorealistic" in p and "No text" in p and ratio == "9:16"
        assert "서준호" not in p and "Seo" not in p and "Junho" not in p        # 이름은 자막 전용
        assert not re.search(r"\b(mascot|fur|animal|bear)\b", p, re.I)    # 백곰 동물 문구 없음
        if key != "front":
            assert "IDENTICAL face" in p                                      # 같은 얼굴 유지
    daily = [sc._aspect_prompt(core, k)[0] for k in ("front", "daily_threequarter", "daily_full", "office_full")]
    assert all("thick-rimmed glasses" in p and "stubble" in p and "NOT gross" in p for p in daily)
    glow = [sc._aspect_prompt(core, k)[0] for k in ("glow_front", "glow_side", "workout_full", "gym_shirtless")]
    assert all("NO glasses" in p and "swept back" in p and "NOT a bodybuilder" in p for p in glow)
    assert "slippers" in daily[2] and "lanyard" in daily[3] and "wrinkled" in daily[3]
    assert "gray hoodie" in glow[2] and "neon lime-green running shoes" in glow[2]
    assert "shirtless" in glow[3] and "NON-sexual" in glow[3] and "gym" in glow[3]
    assert "Change ONLY the hair, glasses and grooming" in glow[0]


def test_generate_all_bases_and_r2_keys(env):
    sc.run_generation(CH, ROLE)
    prog = sc.get_progress(CH, ROLE)
    assert prog["status"] == "done" and prog["generated"] == sc.ASPECT_KEYS and prog["total"] == 8
    assert len(env.t2i.calls) == 1 and env.t2i.calls[0].reference_images is None
    assert len(env.kontext.calls) == 7
    refs = {Path(c.output_path).stem: Path(c.reference_images[0]).stem for c in env.kontext.calls}
    assert refs == {k: sc.aspect_base(k) for k in sc.ASPECT_KEYS[1:]}
    keys = {k for k in env.s3.objs if k.endswith(".png")}
    assert keys == {f"cast/workout_music/lead/{a}.png" for a in sc.ASPECT_KEYS}
    cast = sc.list_cast(CH)
    assert cast[0]["status"] == "draft" and set(cast[0]["aspects"]) == set(sc.ASPECT_KEYS)
    assert cast[0]["subtitle_name"] == "서준호"
    assert cast[0]["aspects"]["front"].startswith("https://img.test/cast/workout_music/lead/front.png?v=")


def test_glow_front_failure_falls_back_to_front(env):
    env.kontext.fail = {"glow_front"}
    sc.run_generation(CH, ROLE)
    p = sc.get_progress(CH, ROLE)
    assert p["status"] == "done" and p["failed"] == ["glow_front"]
    refs = {Path(c.output_path).stem: Path(c.reference_images[0]).stem for c in env.kontext.calls}
    assert refs["glow_side"] == refs["workout_full"] == refs["gym_shirtless"] == "front"
    env.t2i.fail = {"front"}
    sc.run_generation(CH, ROLE)
    p = sc.get_progress(CH, ROLE)
    assert p["status"] == "failed" and p["failed"] == sc.ASPECT_KEYS


def test_approve_version_and_regenerate(env):
    sc.run_generation(CH, ROLE)
    assert sc.reference_urls(CH, ROLE) == []                              # 미확정 → 레퍼런스 없음
    sc.set_status(CH, ROLE, "approved")
    assert sc.list_cast(CH)[0]["status"] == "approved"
    assert sc.reference_urls(CH, ROLE) == ["https://img.test/cast/workout_music/lead/front.png",
                                           "https://img.test/cast/workout_music/lead/glow_front.png"]
    # 이전 바이블(v1)로 확정한 시트 → 검토 중으로 돌아감
    import json
    env.s3.add("cast/workout_music/state.json", json.dumps({ROLE: {"status": "approved"}}).encode())
    assert sc.list_cast(CH)[0]["status"] == "draft" and sc.reference_urls(CH, ROLE) == []
    sc.set_status(CH, ROLE, "approved")
    out = sc.regenerate_aspect(CH, ROLE, "gym_shirtless")
    assert out["url"].startswith("https://img.test/cast/workout_music/lead/gym_shirtless.png?v=")
    assert "warning" not in out
    assert env.kontext.calls[-1].reference_images == ["https://img.test/cast/workout_music/lead/glow_front.png"]
    assert sc.list_cast(CH)[0]["status"] == "draft"                        # 바뀌면 다시 승인
    out = sc.regenerate_aspect(CH, ROLE, "glow_front")
    assert "반전 측면" in out["warning"] and "운동복 전신" in out["warning"]
    assert env.kontext.calls[-1].reference_images == ["https://img.test/cast/workout_music/lead/front.png"]
    out = sc.regenerate_aspect(CH, ROLE, "front")
    assert "기준 얼굴" in out["warning"] and len(env.t2i.calls) == 2


def test_regenerate_requires_front_and_valid_aspect(env):
    with pytest.raises(RuntimeError):
        sc.regenerate_aspect(CH, ROLE, "glow_side")
    with pytest.raises(ValueError):
        sc.regenerate_aspect(CH, ROLE, "expr_sad")
    with pytest.raises(ValueError):
        sc.regenerate_aspect(CH, "nobody", "glow_side")
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
    assert c.post("/shorts/cast/aspect", json={"aspect": "daily_full"}).json()["aspect"] == "daily_full"
    sc._set(CH, ROLE, status="running")
    assert c.post("/shorts/cast/generate", json={}).status_code == 409
