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
    assert sc.ANCHOR == "glow_front"
    assert sc.ASPECT_KEYS == ["glow_front", "glow_side", "gym_shirtless", "workout_full",
                              "glow_outing_full", "daily_front", "daily_threequarter", "daily_full"]
    assert sc.ASPECT_LABELS["glow_front"].startswith("반전 정면") and sc.ASPECT_LABELS["daily_full"] == "평소 전신"
    # 기준 얼굴(반전 정면) 외 7장은 모두 기준 얼굴을 레퍼런스로
    assert [sc.aspect_base(k) for k in sc.ASPECT_KEYS] == [None] + ["glow_front"] * 7


def test_bible_and_prompts():
    e = sc.get_entry(CH, ROLE)
    core = e["core"]
    assert "26-year-old East Asian man" in core and e["subtitle_name"] == "서준호"
    assert e["story"]["places"] == ["원룸", "편의점", "동네 공원", "체육관", "한강"]
    prompts = {k: sc._aspect_prompt(core, k) for k in sc.ASPECT_KEYS}
    for key, (p, ratio) in prompts.items():
        assert "ORIGINAL fictional person" in p and "not resembling" in p and "anime" in p
        assert "Photorealistic" in p and "No text" in p and ratio == "9:16"
        assert "서준호" not in p and "Seo" not in p and "Junho" not in p        # 이름은 자막 전용
        assert not re.search(r"\b(office|employee|lanyard|badge|company|commute)\b", p, re.I)  # 회사원 설정 삭제
        assert not re.search(r"\b(mascot|fur|animal|bear)\b", p, re.I)    # 백곰 동물 문구 없음
        if key != sc.ANCHOR:
            assert "IDENTICAL face" in p and "apparent age" in p              # 같은 얼굴·나이 유지
    anchor = prompts["glow_front"][0]
    assert "comma hairstyle" in anchor and "fashion-editorial" in anchor and "mid-twenties" in anchor
    assert "Using the reference" not in anchor                              # t2i
    glow = [prompts[k][0] for k in ("glow_side", "gym_shirtless", "workout_full", "glow_outing_full")]
    assert all("no glasses" in p and "NOT a bodybuilder" in p for p in glow)
    assert "shirtless" in glow[1] and "NON-sexual" in glow[1] and "gym" in glow[1]
    assert "gray hoodie" in glow[2] and "neon lime-green running shoes" in glow[2]
    assert "reunion" in glow[3]
    daily = [prompts[k][0] for k in ("daily_front", "daily_threequarter", "daily_full")]
    assert all("bedhead" in p and "thick black-rimmed glasses" in p and "dark circles" in p
               and "slouched" in p and "NOT gross" in p for p in daily)
    assert "saggy stretched-out knees" in daily[2] and "slippers" in daily[2] and "convenience-store" in daily[2]
    # 전신 3장만 모델 비율·머리~발끝·낮은 앵글
    for k, (p, _) in prompts.items():
        full = k in ("workout_full", "glow_outing_full", "daily_full")
        assert ("182 cm" in p and "eight heads" in p and "low camera angle" in p) == full, k


def test_generate_all_anchor_first_and_r2_keys(env):
    sc.run_generation(CH, ROLE)
    prog = sc.get_progress(CH, ROLE)
    assert prog["status"] == "done" and prog["generated"] == sc.ASPECT_KEYS and prog["total"] == 8
    assert len(env.t2i.calls) == 1 and Path(env.t2i.calls[0].output_path).stem == "glow_front"
    assert env.t2i.calls[0].reference_images is None
    assert len(env.kontext.calls) == 7
    assert all(Path(c.reference_images[0]).stem == "glow_front" for c in env.kontext.calls)
    keys = {k for k in env.s3.objs if k.endswith(".png")}
    assert keys == {f"cast/workout_music/lead/{a}.png" for a in sc.ASPECT_KEYS}
    cast = sc.list_cast(CH)
    assert cast[0]["status"] == "draft" and set(cast[0]["aspects"]) == set(sc.ASPECT_KEYS)
    assert cast[0]["subtitle_name"] == "서준호"


def test_partial_and_anchor_failure(env):
    env.kontext.fail = {"glow_side"}
    sc.run_generation(CH, ROLE)
    p = sc.get_progress(CH, ROLE)
    assert p["status"] == "done" and p["failed"] == ["glow_side"]
    env.t2i.fail = {"glow_front"}
    sc.run_generation(CH, ROLE)
    p = sc.get_progress(CH, ROLE)
    assert p["status"] == "failed" and p["failed"] == sc.ASPECT_KEYS


def test_approve_version_and_regenerate(env):
    sc.run_generation(CH, ROLE)
    assert sc.reference_urls(CH, ROLE) == []                              # 미확정 → 레퍼런스 없음
    sc.set_status(CH, ROLE, "approved")
    assert sc.list_cast(CH)[0]["status"] == "approved"
    assert sc.reference_urls(CH, ROLE) == ["https://img.test/cast/workout_music/lead/glow_front.png",
                                           "https://img.test/cast/workout_music/lead/daily_front.png"]
    # 이전 바이블(v2)로 확정한 시트 → 검토 중으로 돌아감
    import json
    env.s3.add("cast/workout_music/state.json", json.dumps({ROLE: {"status": "approved", "version": 2}}).encode())
    assert sc.list_cast(CH)[0]["status"] == "draft" and sc.reference_urls(CH, ROLE) == []
    sc.set_status(CH, ROLE, "approved")
    out = sc.regenerate_aspect(CH, ROLE, "daily_full")
    assert out["url"].startswith("https://img.test/cast/workout_music/lead/daily_full.png?v=")
    assert "warning" not in out
    assert env.kontext.calls[-1].reference_images == ["https://img.test/cast/workout_music/lead/glow_front.png"]
    assert sc.list_cast(CH)[0]["status"] == "draft"                        # 바뀌면 다시 승인
    out = sc.regenerate_aspect(CH, ROLE, "glow_front")
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
    assert r["anchor"] == "glow_front"
    assert c.get("/shorts/cast?channel=sayeon").status_code == 404
    assert c.post("/shorts/cast/generate", json={"channel": CH, "role": ROLE}).json()["status"] == "running"
    assert c.get("/shorts/cast/status").json()["status"] == "done"            # TestClient 는 백그라운드를 끝까지 실행
    assert c.post("/shorts/cast/approve", json={"approved": True}).json()["status"] == "approved"
    assert c.post("/shorts/cast/aspect", json={"aspect": "bad"}).status_code == 400
    assert c.post("/shorts/cast/aspect", json={"aspect": "daily_full"}).json()["aspect"] == "daily_full"
    sc._set(CH, ROLE, status="running")
    assert c.post("/shorts/cast/generate", json={}).status_code == 409
