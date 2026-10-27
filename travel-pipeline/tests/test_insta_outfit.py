"""인스타 착장(A1) — 장면 규칙·연속 금지·아이웨어 빈도·프롬프트·전체 흐름(가짜 Muse·비전·저장소, 실제 ffmpeg)."""

from __future__ import annotations

import random
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.base import ImageGenerationResult  # noqa: E402
from services import character_studio as cs  # noqa: E402
from services import insta_outfit as io  # noqa: E402
from services import insta_outfit_plan as P  # noqa: E402
from test_character_studio import studio  # noqa: E402,F401
from test_shorts_cast import env  # noqa: E402,F401

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=P.KST)  # 일요일, 가을
SHOES = [{"kind": "top", "url": "u1"}, {"kind": "bottoms", "url": "u2"}, {"kind": "shoes", "url": "u3"}]
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 필요")


def _hist(*plans, days_ago=1):
    return [{"plan": p, "created_at": (NOW - timedelta(days=days_ago)).isoformat()} for p in plans]


# ── 규칙 ─────────────────────────────────────────────────────────────────
def test_compatible_scene_rules():
    shoe_poses = [k for k, v in P.POSES.items() if v["feet"] == "shoes"]
    assert shoe_poses and not any(P.compatible(p, "room") for p in shoe_poses)        # 신발 보이는 컷 방 금지
    assert P.compatible("floor_mirror", "room") and not P.compatible("floor_mirror", "cafe")  # 양말은 방 전용
    # 2026-10-27: 셀카 느낌만 — 제3자 시점 포즈는 꺼짐
    assert P.SELF_SHOT_ONLY and not P.compatible("bench_side", "park_bench") and not P.compatible("walk_toward", "street")
    assert P.compatible("sit_look_down", "park_bench") and P.compatible("glass_reflection", "street")
    assert not P.compatible("mirror_lean", "street") and P.compatible("mirror_lean", "elevator_mirror")
    for lk, loc in P.LOCATIONS.items():
        for pk, pose in P.POSES.items():
            if P.compatible(pk, lk) and loc["kind"] == "room":
                assert pose["feet"] != "shoes"


def test_candidates_shoes_product_avoids_room():
    c = P.candidates(weekday=6, products=SHOES, hair_roles=["hair_01_straight"], history=[], now=NOW)
    assert c["pairs"] and all(P.LOCATIONS[l]["kind"] != "room" for l, _ in c["pairs"])
    c2 = P.candidates(weekday=6, products=SHOES[:2], hair_roles=[], history=[], now=NOW)
    room_poses = {p for l, p in c2["pairs"] if l == "room"}
    assert room_poses and all(P.POSES[p]["feet"] != "shoes" for p in room_poses)    # 방 = 양말·발 안 보임
    assert "detail_bag" not in {p for _, p in c2["pairs"]}                           # 가방 없으면 가방 컷 없음


def test_three_in_a_row_blocked():
    h = _hist({"location": "cafe", "pose": "cafe_cross", "hair_role": "hair_02_wave"},
              {"location": "cafe", "pose": "cafe_cross", "hair_role": "hair_02_wave"})
    c = P.candidates(weekday=5, products=SHOES, hair_roles=["hair_02_wave", "hair_05_ponytail"], history=h, now=NOW)
    assert "cafe" not in {l for l, _ in c["pairs"]} and "cafe_cross" not in {p for _, p in c["pairs"]}
    assert c["hairs"] == ["hair_05_ponytail"]
    h2 = _hist({"location": "cafe"}, {"location": "park_bench"})                     # 2연속 아님 → 허용
    assert "cafe" in {l for l, _ in P.candidates(weekday=5, products=SHOES, hair_roles=[], history=h2, now=NOW)["pairs"]}


def test_entry_mirror_twice_a_week():
    h = _hist({"location": "entry_mirror"}, {"location": "office_lobby"}, days_ago=2) + \
        _hist({"location": "entry_mirror"}, days_ago=3)
    c = P.candidates(weekday=0, products=SHOES, hair_roles=[], history=h, now=NOW)
    assert "entry_mirror" not in {l for l, _ in c["pairs"]} and c["notes"]
    old = _hist({"location": "entry_mirror"}, {"location": "entry_mirror"}, days_ago=9)
    old = [{"plan": {"location": "x"}, "created_at": NOW.isoformat()}] + old          # 7일 밖은 세지 않음
    assert "entry_mirror" in {l for l, _ in P.candidates(weekday=0, products=SHOES, hair_roles=[], history=old, now=NOW)["pairs"]}


def test_eyewear_frequency_and_no_repeat():
    rng = random.Random(7)
    assert P.choose_eyewear(_hist({"eyewear": None}, {"eyewear": None}), rng) is not None
    assert P.choose_eyewear(_hist({"eyewear": {"item": "clear_acetate", "style": "wear"}}, {}), rng) is None
    history: list[dict] = []
    used = []
    for _ in range(300):
        ew = P.choose_eyewear(history, rng)
        if ew and used and used[-1]:
            pytest.fail("직전에 썼는데 또 씀")
        if ew and history and any((h.get("plan") or {}).get("eyewear") for h in history[:3]):
            last = next(h["plan"]["eyewear"]["item"] for h in history if (h.get("plan") or {}).get("eyewear"))
            assert ew["item"] != last                                                  # 같은 아이템 연속 금지
        used.append(ew)
        history.insert(0, {"plan": {"eyewear": ew}})
    ratio = sum(1 for e in used if e) / len(used)
    assert 0.25 <= ratio <= 0.42, ratio                                                # 3번 중 1번 정도
    assert P.choose_eyewear([], rng, "none") is None
    assert P.choose_eyewear([], rng, "metal_round")["item"] == "metal_round"


def test_plan_scene_ai_pick_and_fallbacks():
    def llm_ok(system, user):
        return '{"pair": 0, "hair_role": "hair_05_ponytail", "weather_en": "crisp autumn", "reason": "주말 산책"}'
    p = P.plan_scene(character_id="chaei", products=SHOES, hair_roles=["hair_05_ponytail"], history=[], now=NOW,
                     rng=random.Random(1), llm=llm_ok)
    assert p["source"] == "ai" and p["hair_role"] == "hair_05_ponytail" and p["reason"] == "주말 산책"
    assert p["season"] == "autumn" and p["weekday"] == 6
    bad = P.plan_scene(character_id="chaei", products=SHOES, hair_roles=["hair_05_ponytail"], history=[], now=NOW,
                       rng=random.Random(1), llm=lambda s, u: '{"pair": 999, "hair_role": "nope"}')
    assert bad["source"] == "random" and bad["hair_role"] == "hair_05_ponytail"
    boom = P.plan_scene(character_id="chaei", products=SHOES, hair_roles=[], history=[], now=NOW,
                        rng=random.Random(1), llm=lambda s, u: (_ for _ in ()).throw(RuntimeError("api down")))
    assert boom["source"] == "random" and P.compatible(boom["pose"], boom["location"])


def test_plan_never_breaks_rules_randomized():
    for seed in range(300):
        rng = random.Random(seed)
        prods = SHOES if seed % 2 else SHOES[:2]
        p = P.plan_scene(character_id="c", products=prods, hair_roles=["hair_01_straight"], history=[],
                         options={"weekday": seed % 7}, now=NOW, rng=rng, llm=lambda s, u: "{}")
        assert P.compatible(p["pose"], p["location"])
        if any(x["kind"] == "shoes" for x in prods):
            assert P.LOCATIONS[p["location"]]["kind"] != "room"


def test_user_override_conflict_is_fixed():
    p = P.plan_scene(character_id="c", products=SHOES, hair_roles=[], history=[], now=NOW, rng=random.Random(3),
                     options={"location": "room", "pose": "crosswalk_walk"}, llm=lambda s, u: "{}")
    assert P.compatible(p["pose"], p["location"]) and p["notes"]


# ── 프롬프트 ─────────────────────────────────────────────────────────────
def _plan(**kw):
    base = {"location": "elevator_mirror", "pose": "mirror_lean", "season": "autumn", "weather_en": "a crisp autumn day",
            "eyewear": None}
    return {**base, **kw}


def test_build_prompt_and_refs():
    prods = [{"kind": "top", "url": "t"}, {"kind": "bottoms", "url": "b"}, {"kind": "shoes", "url": "s"},
             {"kind": "bag", "url": "g", "revealing": False}]
    prompt, refs = P.build(_plan(), face_url="F", body_url="B", hair_url="H", products=prods)
    assert refs == ["F", "B", "H", "t", "b", "s", "g"]
    assert prompt.startswith("Same woman as reference images 1 and 2 — same face shape, black hair color and the same "
                             "body shape as the reference, with the hairstyle from image 3. Take only the clothing")
    assert ("She is wearing exactly the top from image 4, the bottoms from image 5, the shoes from image 6, carrying "
            "the bag from image 7 — keep every garment detail identical") in prompt
    assert "phone held up covering her face" in prompt and prompt.endswith("no retouching.")
    assert "bust" not in prompt.lower() and "cropped at the neck" not in prompt


def test_build_room_socks_revealing_eyewear_fix():
    prods = [{"kind": "top", "url": "t", "revealing": True}, {"kind": "shoes", "url": "s"}]
    prompt, refs = P.build(_plan(location="room", pose="bed_edge",
                                 eyewear={"item": "black_sunglasses", "style": "head"}),
                           face_url="F", body_url="B", hair_url=None, products=prods, fix_hint="shoes visible indoors.")
    assert refs == ["F", "B", "t"] and "the top from image 3" in prompt and "shoes" not in prompt.split("Take only")[1].split("She is in socks")[0]
    assert "with her usual long black hair" in prompt and "She is in socks, no shoes." in prompt
    assert "plain fitted top underneath" in prompt and "pushed up on top of her head" in prompt
    assert "framed from the shoulders down so her face is not visible" in prompt
    assert prompt.endswith("Important fix from the last attempt: shoes visible indoors.")
    sun, _ = P.build(_plan(location="street", pose="walk_toward", eyewear={"item": "black_sunglasses", "style": "wear"}),
                     face_url="F", body_url="B", hair_url="H", products=prods[:1])
    assert "only the lower part of her face visible" in sun


def test_build_flatlay_and_ref_cap():
    prods = [{"kind": "top", "url": "t"}, {"kind": "shoes", "url": "s"}]
    prompt, refs = P.build(_plan(location="entry_mirror", pose="flatlay"), face_url="F", body_url="B", hair_url="H",
                           products=prods)
    assert refs == ["t", "s"] and prompt.startswith("Flat lay photo with no person: the top from image 1, the shoes from image 2")
    many = [{"kind": "accessory", "url": f"a{i}"} for i in range(12)]
    _, refs = P.build(_plan(), face_url="F", body_url="B", hair_url="H", products=many)
    assert len(refs) == 10 and refs[:3] == ["F", "B", "H"]


# ── 전체 흐름(가짜 Muse·비전·저장소) ─────────────────────────────────────
class _FakeOutfitRest:
    def __init__(self):
        self.rows: list[dict] = []

    def __call__(self, method, *, params=None, json_body=None, prefer=None):
        params = params or {}
        def match(r):
            for k, v in params.items():
                if k in ("select", "order", "limit"):
                    continue
                if str(r.get(k)) != v.split(".", 1)[1]:
                    return False
            return True
        if method == "GET":
            out = [dict(r) for r in self.rows if match(r)]
            return sorted(out, key=lambda r: r.get("created_at", ""), reverse=True)[: int(params.get("limit", 999))]
        if method == "POST":
            for rec in json_body:
                self.rows.append({"created_at": datetime.now().isoformat(), "plan": {}, "attempts": 0, **rec})
            return [dict(self.rows[-1])]
        if method == "PATCH":
            for r in self.rows:
                if match(r):
                    r.update(json_body)
            return []
        raise AssertionError(method)


class _FakeMuse:
    def __init__(self):
        self.calls = []

    def is_available(self):
        return True

    async def generate(self, req):
        self.calls.append(req)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=teal:s=576x1024",
                        "-frames:v", "1", req.output_path], check=True)
        return ImageGenerationResult(image_path=req.output_path, cost_usd=0.011, model_used="muse", raw_response={})


@pytest.fixture
def flow(studio, monkeypatch, tmp_path):  # noqa: F811
    rest, muse = _FakeOutfitRest(), _FakeMuse()
    monkeypatch.setattr(io, "_rest", rest)
    monkeypatch.setattr(io, "get_muse_adapter", lambda: muse)
    monkeypatch.setattr(io, "_download", lambda url, dest: (subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=800x800", "-frames:v", "1", str(dest)],
        check=True), dest)[1])
    monkeypatch.setattr(P, "plan_scene", _wrap_plan(P.plan_scene))
    for role in ("01_face", "02_body", "hair_05_ponytail"):
        ref = cs.insert_ref("chaei", role, r2_key=f"characters/chaei/{role}/x.png", url=f"https://img.test/{role}.png",
                            source="upload")
        cs.confirm_ref(ref["id"])
    from services import character_measurements as cm
    cm.save("chaei", cm.DRAFTS["chaei"])
    io._JOBS.clear()
    io._ACTIVE.clear()
    studio.rest_out, studio.muse = rest, muse
    return studio


def _wrap_plan(fn):
    def inner(**kw):
        kw.setdefault("llm", lambda s, u: "{}")
        return fn(**kw)
    return inner


PRODS = [{"key": "insta/products/upload/abc123/0.png", "kind": "top"},
         {"key": "insta/products/upload/abc123/1.png", "kind": "shoes"}]


@needs_ffmpeg
def test_flow_review_retry_then_ok(flow, monkeypatch):
    verdicts = iter([{"pass": False, "violations": [{"type": "face_visible", "detail": "얼굴 보임"}], "fix_en": "hide her face"},
                     {"pass": True, "violations": []}])
    monkeypatch.setattr(io, "_vision_json", lambda *a, **k: {**next(verdicts), "_model": "fake"})
    job = io.start("chaei", PRODS, {"weekday": 6})
    assert io.start("chaei", PRODS, {"weekday": 6})["id"] == job["id"]                # 같은 요청 → 같은 잡
    io.run(job["id"], rng=random.Random(2))
    j = io.get_job(job["id"])
    assert j["state"] == "done" and j["status"] == "ok" and j["attempts"] == 2
    row = flow.rest_out.rows[0]
    assert row["status"] == "ok" and row["attempts"] == 2 and row["cost_usd"] == 0.022
    assert row["image_key"] == f"insta/outfits/{row['id']}/original.png" and row["processed_key"].endswith("processed.jpg")
    assert flow.s3.objs[row["processed_key"]][0][:3] == b"\xff\xd8\xff"               # jpg 처리본
    assert "Important fix from the last attempt: hide her face." in flow.muse.calls[1].prompt
    refs = flow.muse.calls[0].reference_images
    assert refs[:3] == ["https://img.test/01_face.png", "https://img.test/02_body.png", "https://img.test/hair_05_ponytail.png"]
    assert flow.muse.calls[0].aspect_ratio == "9:16"
    assert P.LOCATIONS[row["plan"]["location"]]["kind"] != "room"                      # 일요일 + 신발 → 방 아님
    assert len(row["review"]["history"]) == 2
    assert io.start("chaei", PRODS, {"weekday": 6})["id"] != job["id"]                # 끝난 뒤엔 새 잡


@needs_ffmpeg
def test_flow_review_failed_keeps_image(flow, monkeypatch):
    monkeypatch.setattr(io, "_vision_json", lambda *a, **k: {"pass": False, "violations": [{"type": "anatomy", "detail": "손가락 6개"}],
                                                            "fix_en": "", "_model": "fake"})
    job = io.start("chaei", PRODS)
    io.run(job["id"], rng=random.Random(4))
    row = flow.rest_out.rows[0]
    assert row["status"] == "review_failed" and row["attempts"] == 3 and row["image_key"]
    assert row["review"]["violations"][0]["detail"] == "손가락 6개"


@needs_ffmpeg
def test_flow_review_call_error_passes_with_note(flow, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("anthropic down")
    monkeypatch.setattr(io, "_vision_json", boom)
    job = io.start("chaei", PRODS)
    io.run(job["id"], rng=random.Random(5))
    row = flow.rest_out.rows[0]
    assert row["status"] == "ok" and row["attempts"] == 1 and "검수 호출 실패" in row["review"]["skipped"]


def test_start_validation(flow):
    with pytest.raises(io.OutfitError, match="종류"):
        io.start("chaei", [{"key": "insta/products/upload/abc123/0.png", "kind": ""}])
    with pytest.raises(io.OutfitError, match="1~4"):
        io.start("chaei", [])
    with pytest.raises(io.OutfitError, match="이 화면에서"):
        io.start("chaei", [{"key": "characters/chaei/01_face/x.png", "kind": "top"}])
    cs.upsert_character("mina", "미나")
    with pytest.raises(io.OutfitError, match="준비 완료"):
        io.start("mina", PRODS)
    for role in ("01_face", "02_body"):
        ref = cs.insert_ref("mina", role, r2_key=f"characters/mina/{role}/x.png", url="u", source="upload")
        cs.confirm_ref(ref["id"])
    with pytest.raises(io.OutfitError, match="치수"):
        io.start("mina", PRODS)


@needs_ffmpeg
def test_save_product_with_kind_suggestion(flow, monkeypatch, tmp_path):
    img = tmp_path / "coat.jpg"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=900x1200", "-frames:v", "1", str(img)], check=True)
    monkeypatch.setattr(io, "_vision_json", lambda *a, **k: {"kind": "outerwear", "desc": "camel wool coat", "revealing": False})
    out = io.save_product("abc123", 0, img.read_bytes(), "coat.jpg")
    assert out["key"] == "insta/products/upload/abc123/0.png" and out["kind"] == "outerwear" and out["desc"] == "camel wool coat"
    assert flow.s3.objs[out["key"]][0][:8] == b"\x89PNG\r\n\x1a\n"
    monkeypatch.setattr(io, "_vision_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    out = io.save_product("abc123", 1, img.read_bytes(), "coat.jpg")
    assert out["kind"] is None and out["suggest_error"]                                # 추천 실패해도 업로드 성공
    with pytest.raises(io.OutfitError):
        io.save_product("BAD!", 0, img.read_bytes(), "a.jpg")


@needs_ffmpeg
def test_api_routes(flow, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import insta as routes

    monkeypatch.setattr(io, "_vision_json", lambda *a, **k: {"pass": True, "violations": [], "_model": "fake"})
    app = FastAPI()
    app.include_router(routes.router, prefix="/insta")
    c = TestClient(app)
    opts = c.get("/insta/outfit-options").json()
    assert len(opts["poses"]) == 15 and len(P.POSES) == 25 and opts["estimate"]["max"] == 0.033
    r = c.post("/insta/outfits", json={"character_id": "chaei", "products": PRODS})
    assert r.status_code == 200
    j = c.get(f"/insta/outfit-jobs/{r.json()['id']}").json()
    assert j["state"] == "done" and "_args" not in j
    lst = c.get("/insta/outfits", params={"character_id": "chaei"}).json()["outfits"]
    assert lst[0]["processed_url"].endswith("processed.jpg")
    assert c.post(f"/insta/outfits/{lst[0]['id']}/remake").status_code == 200
    assert c.post("/insta/outfits", json={"products": []}).status_code == 400
    assert c.get("/insta/outfits/of-20990101-zzzz").status_code == 404


# ── 꾸안꾸 셀카(2026-10-27 대표 레퍼런스) ──────────────────────────────────
def test_kkuankku_plan_face_eyewear_and_prompt():
    rng = random.Random(3)
    for _ in range(30):
        plan = P.plan_scene(character_id="chaei", products=PRODS, hair_roles=[], history=[], now=NOW, rng=rng, llm=lambda s, u: "{}",
                      options={"pose": "closeup_sunglasses", "location": "cafe"})
        if plan["pose"] == "closeup_sunglasses":
            break
    assert plan["face"] == "sunglasses" and plan["eyewear"]["style"] == "wear" and P.EYEWEAR[plan["eyewear"]["item"]]["sun"]
    prompt, _ = P.build(plan, face_url="f", body_url="b", hair_url=None, products=[{"url": "u", "kind": "top"}])
    assert "rosy lip tint" in prompt and "꾸안꾸" in prompt and "no pearls" in prompt
    assert "early 20s" in prompt and "never mature" in prompt                          # 노티 금지(2026-10-27)
    crop = {**plan, "pose": "arm_selfie_high", "face": "chin_crop", "eyewear": None, "prop": "holding an iced americano"}
    prompt, _ = P.build(crop, face_url="f", body_url="b", hair_url=None, products=[{"url": "u", "kind": "top"}])
    assert "just below the eyes" in prompt and "iced americano" in prompt and "took this photo herself" in prompt
    terrace = {**plan, "pose": "cafe_terrace"}
    prompt, _ = P.build(terrace, face_url="f", body_url="b", hair_url=None, products=[{"url": "u", "kind": "top"}])
    assert "a friend took" in prompt and "took this photo herself" not in prompt


def test_face_selfie_is_occasional_and_mood():
    rng = random.Random(7)
    faces, moods, prev = 0, 0, []
    for _ in range(60):
        plan = P.plan_scene(character_id="chaei", products=PRODS, hair_roles=[], history=prev, now=NOW, rng=rng,
                            llm=lambda s, u: "{}")
        if plan["face"] == "full":
            faces += 1
            assert not (prev and prev[0]["plan"].get("face") == "full")                  # 얼굴 셀카 연속 금지
        moods += bool(plan.get("mood"))
        prev = [{"plan": plan, "created_at": NOW.isoformat()}] + prev[:4]
    assert 3 <= faces <= 25 and moods >= 25
    plan = {**plan, "pose": "face_selfie", "face": "full", "mood": "a big carefree smile", "prop": None, "eyewear": None}
    prompt, _ = P.build(plan, face_url="f", body_url="b", hair_url=None, products=[{"url": "u", "kind": "top"}])
    assert "exactly like reference image 1" in prompt and "Free-spirited mood" in prompt and "photo diary" in prompt
