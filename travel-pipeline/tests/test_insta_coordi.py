"""A2-3a — 내 상품으로 코디: 링크 검사·쇼핑몰 자동 · 빈 종류 결정 · 채우기 명세 · 전체 흐름(가짜 쿠팡·비전·Muse·저장소)
· 쿠팡 이미지 쓰고 지우기(완료·실패 모두) · 승인/반려 · 내리기 · API."""

from __future__ import annotations

import json
import random
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import insta_coordi as C  # noqa: E402
from services import insta_outfit as io  # noqa: E402
from services import insta_picks as K  # noqa: E402
from services import insta_refs as R  # noqa: E402
from test_character_studio import studio  # noqa: E402,F401
from test_insta_outfit import flow  # noqa: E402,F401
from test_insta_picks import _c, _dl, _Shop, _Tables, _vision  # noqa: E402
from test_shorts_cast import env  # noqa: E402,F401

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 필요")
BOSE = [{"key": "insta/products/upload/abc123/0.png", "kind": "top", "desc": "ivory wool knit",
         "link": "https://www.musinsa.com/products/123", "name": "울 니트"}]


# ── 링크·쇼핑몰 ──────────────────────────────────────────────────────────
def test_validate_link():
    assert C.validate_link("") is None and C.validate_link(None) is None
    assert C.validate_link(" https://m.29cm.co.kr/p/1 ") == "https://m.29cm.co.kr/p/1"
    for bad in ("http://musinsa.com/1", "javascript:alert(1)", "https://a b.com", "ftp://x", "https://", "musinsa.com/1",
                "https://" + "a" * 600):
        with pytest.raises(C.CoordiError, match="https://"):
            C.validate_link(bad)


def test_mall_from_link():
    assert C.mall_from_link("https://www.musinsa.com/products/1") == "무신사"
    assert C.mall_from_link("https://m.29cm.co.kr/p/1") == "29CM"
    assert C.mall_from_link("https://shop.example.co.kr/item") == "example"
    assert C.mall_from_link("https://www.mybose.com/a") == "mybose"
    assert C.mall_from_link("https://www.musinsa.com/1", "  보세집  ") == "보세집"            # 직접 적은 이름 우선
    assert C.mall_from_link(None) is None


# ── 빈 종류 ──────────────────────────────────────────────────────────────
def test_missing_kinds():
    assert C.missing_kinds(["top"], "summer") == ["bottoms", "shoes", "bag"]                # 니트만 → 하의·신발·가방
    assert C.missing_kinds(["bottoms"], "summer") == ["top", "shoes", "bag"]
    assert C.missing_kinds(["dress"], "autumn") == ["shoes", "bag", "outerwear"]            # 원피스 → 상·하의 없음
    assert C.missing_kinds(["dress"], "summer") == ["shoes", "bag"]                         # 여름엔 아우터 없음
    assert C.missing_kinds(["top", "bottoms"], "winter") == ["shoes", "bag"]                # 합계 4 넘지 않음
    assert C.missing_kinds(["shoes"], "spring") == ["bottoms", "top", "bag"]
    assert C.missing_kinds(["top", "bottoms", "shoes", "bag"], "winter") == []


def test_fill_specs_ai_and_fallback():
    def llm(system, user):
        assert json.loads(user)["need"] == ["bottoms", "shoes"]
        return json.dumps({"concept": "가을 출근", "items": [
            {"kind": "bottoms", "color_name": "차콜", "hex": "#36454F", "fit": "regular", "queries": ["여성 차콜 슬랙스"]},
            {"kind": "hat", "queries": ["모자"]}]})
    concept, items = C.fill_specs(BOSE, ["bottoms", "shoes"], "autumn", llm)
    assert concept == "가을 출근" and [i["kind"] for i in items] == ["bottoms", "shoes"]
    assert items[0]["queries"] == ["여성 차콜 슬랙스"] and items[1]["queries"] == ["여성 블랙 로퍼"]   # 빠진 종류는 기본
    concept, items = C.fill_specs(BOSE, ["bag"], "autumn", lambda s, u: (_ for _ in ()).throw(RuntimeError("down")))
    assert concept == "내 상품 코디" and items[0]["queries"] == ["여성 블랙 숄더백"]


# ── 전체 흐름 ────────────────────────────────────────────────────────────
FILL_LLM = lambda s, u: json.dumps({"concept": "가을 니트룩", "items": [  # noqa: E731
    {"kind": "bottoms", "color_name": "차콜", "hex": "#36454F", "queries": ["차콜 슬랙스 여성"]},
    {"kind": "shoes", "color_name": "블랙", "hex": "#111111", "queries": ["블랙 로퍼 여성"]},
    {"kind": "bag", "color_name": "블랙", "hex": "#111111", "queries": ["블랙 숄더백 여성"]}]})
SCORES = {"coupang_c4": (9, "#36454F"), "coupang_c5": (8, "#36454F"), "coupang_s1": (9, "#111111"), "coupang_b1": (9, "#111111")}


def _shop():
    return _Shop("coupang", {
        "차콜 슬랙스 여성": [_c("c4", "여성 차콜 와이드 슬랙스", ch="coupang") | {"link": "https://www.coupang.com/vp/4"},
                        _c("c5", "여성 차콜 일자 슬랙스", ch="coupang") | {"link": "https://www.coupang.com/vp/5"}],
        "블랙 로퍼 여성": [_c("s1", "여성 블랙 로퍼", ch="coupang") | {"link": "https://www.coupang.com/vp/6"}],
        "블랙 숄더백 여성": [_c("b1", "여성 블랙 숄더백", ch="coupang") | {"link": "https://www.coupang.com/vp/7"}],
    })


@pytest.fixture
def coordi(flow, monkeypatch):  # noqa: F811
    t = _Tables()
    monkeypatch.setattr(R, "rest", t)
    monkeypatch.setattr(io, "_vision_json", lambda *a, **k: {"pass": True, "violations": [], "_model": "fake"})
    flow.s3.delete_object = lambda Bucket, Key: flow.s3.objs.pop(Key, None)
    flow.s3.add(BOSE[0]["key"], b"\x89PNG")
    C._JOBS.clear()
    flow.t = t
    return flow


def _deps(t, shop=None):
    return K.Deps(coupang=shop or _shop(), vision=_vision(SCORES), download=_dl, rest=t)


@needs_ffmpeg
def test_fill_flow_end_to_end_and_images_deleted(coordi):
    t = coordi.t
    d = _deps(t)
    job = C.start("chaei", BOSE, "fill", d=d)
    assert C.start("chaei", BOSE, "fill", d=d)["id"] == job["id"]                         # 같은 요청 → 같은 잡
    C.run(job["id"], llm=FILL_LLM, rng=random.Random(2))
    j = C.get_job(job["id"])
    assert j["state"] == "done" and j["outfit_id"] and "_deps" not in j
    assert j["cost"]["image_usd"] == 0.011 and j["cost"]["krw"] == round(j["cost"]["usd"] * 1400)
    look = t.t["ig_looks"][0]
    assert look["source"] == "bose" and look["status"] == "picked" and look["concept"] == "가을 니트룩"
    kinds = [(it["kind"], it["source"]) for it in look["items"]]
    assert kinds == [("top", "bose"), ("bottoms", "coupang"), ("shoes", "coupang"), ("bag", "coupang")]
    assert look["items"][1]["pick"]["product_id"] == "c4" and look["items"][1]["backups"][0]["product_id"] == "c5"
    # 착장: 넣은 상품 + 쿠팡 3개, 출처·링크·쇼핑몰
    row = next(r for r in coordi.rest_out.rows if r["id"] == j["outfit_id"])
    assert row["look_id"] == look["id"] and row["caption_note"] == io.CAPTION_NOTE
    srcs = [(p["kind"], p.get("source"), p.get("mall")) for p in row["product_images"]]
    assert srcs == [("top", "bose", "무신사"), ("bottoms", "coupang", None), ("shoes", "coupang", None), ("bag", "coupang", None)]
    assert row["product_images"][0]["link"] == BOSE[0]["link"]
    assert row["product_images"][1]["link"] == "https://link.coupang.com/a/4"            # 쿠팡은 제휴 링크
    assert len(coordi.muse.calls[0].reference_images) == 3 + 4                             # 얼굴·체형·헤어 + 상품 4
    # 쿠팡 이미지: 착장 완료 후 R2 사본 삭제 + image_key 비움 + 삭제 시각 (보세 업로드는 보관)
    prods = {p["product_id"]: p for p in t.t["ig_products"]}
    for pid in ("c4", "c5", "s1", "b1"):
        assert prods[pid]["image_key"] is None and prods[pid]["image_deleted_at"]
    assert not [k for k in coordi.s3.objs if k.startswith("insta/products/coupang/")]
    bose = next(p for p in t.t["ig_products"] if p["channel"] == "bose")
    assert bose["image_key"] == BOSE[0]["key"] and BOSE[0]["key"] in coordi.s3.objs and bose["link"] == BOSE[0]["link"]
    assert all(c.get("image_key") is None for it in look["items"][1:] for c in [it["pick"], *it["backups"]])
    # 화면: 룩이 붙은 착장, 쿠팡은 원본 URL 로 표시(저장 안 함)
    shown = C.attach_looks([row], d)[0]["look"]
    assert shown["items"][1]["pick"]["image"] == "https://i/c4.jpg"
    assert shown["items"][0]["pick"]["image"] == f"https://img.test/{BOSE[0]['key']}"


@needs_ffmpeg
def test_failed_outfit_still_deletes_coupang_images(coordi, monkeypatch):
    t = coordi.t

    async def boom(req):
        raise RuntimeError("wavespeed down")
    monkeypatch.setattr(coordi.muse, "generate", boom)
    job = C.start("chaei", BOSE, "fill", d=_deps(t))
    C.run(job["id"], llm=FILL_LLM, rng=random.Random(2))
    assert C.get_job(job["id"])["state"] == "failed"
    cp = [p for p in t.t["ig_products"] if p["channel"] == "coupang"]
    assert cp and all(p["image_key"] is None and p["image_deleted_at"] for p in cp)       # 실패 확정에도 지움
    assert not [k for k in coordi.s3.objs if k.startswith("insta/products/coupang/")]


@needs_ffmpeg
def test_only_mode_no_coupang_and_quota(coordi):
    t = coordi.t
    shop = _shop()
    job = C.start("chaei", BOSE, "only", d=_deps(t, shop))
    C.run(job["id"], rng=random.Random(3))
    assert C.get_job(job["id"])["state"] == "done" and shop.calls == []                   # 이것만 입히기 = 쿠팡 안 씀
    row = coordi.rest_out.rows[0]
    assert [p["kind"] for p in row["product_images"]] == ["top"]
    # 쿠팡 한도 → 하나도 못 고르면 "잠시 후 다시"
    job = C.start("chaei", BOSE, "fill", d=_deps(t, _Shop("coupang", "quota")))
    C.run(job["id"], llm=FILL_LLM)
    j = C.get_job(job["id"])
    assert j["state"] == "failed" and "잠시 후 다시" in j["error"]
    # 쿠팡 키가 없으면 채우기는 시작 전에 막는다(이것만 입히기는 가능)
    with pytest.raises(C.CoordiError, match="쿠팡 연결"):
        C.start("chaei", BOSE, "fill", d=_deps(t, _Shop("coupang", {}, ok=False)))


def test_start_validation(coordi):
    t = coordi.t
    with pytest.raises(C.CoordiError, match="https://"):
        C.start("chaei", [{**BOSE[0], "link": "http://x.com"}], "only", d=_deps(t))
    with pytest.raises(C.CoordiError, match="이 화면에서"):
        C.start("chaei", [{**BOSE[0], "key": "insta/products/coupang/x.jpg"}], "only", d=_deps(t))
    with pytest.raises(C.CoordiError, match="1~4"):
        C.start("chaei", BOSE * 5, "only", d=_deps(t))
    with pytest.raises(C.CoordiError, match="방식"):
        C.start("chaei", BOSE, "auto", d=_deps(t))
    assert t.t["ig_looks"] == []                                                           # 검증 실패면 아무것도 안 만듦


@needs_ffmpeg
def test_decide_hide_and_feedback(coordi):
    t = coordi.t
    d = _deps(t)
    job = C.start("chaei", BOSE, "fill", d=d)
    C.run(job["id"], llm=FILL_LLM, rng=random.Random(2))
    oid = C.get_job(job["id"])["outfit_id"]
    look_id = t.t["ig_looks"][0]["id"]
    C.decide(oid, "approved", d=d)
    assert io.get_outfit(oid)["decision"] == "approved" and t.t["ig_looks"][0]["status"] == "approved"
    with pytest.raises(C.CoordiError):
        C.decide(oid, "maybe", d=d)
    with pytest.raises(C.CoordiError, match="이유"):
        C.hide_outfit(oid, " ", d=d)
    C.hide_outfit(oid, "판매자 요청", d=d)
    assert io.get_outfit(oid)["hidden_reason"] == "판매자 요청"
    assert oid not in [r["id"] for r in io.list_outfits("chaei")]                          # 내린 착장은 목록에서 빠짐
    assert oid in [r["id"] for r in io.list_outfits("chaei", include_hidden=True)]
    pid = next(p["id"] for p in t.t["ig_products"] if p["product_id"] == "c4")
    C.hide_product(pid, "품절", d=d)
    assert next(p for p in t.t["ig_products"] if p["id"] == pid)["hidden_reason"] == "품절"
    events = [(f["event"], f.get("outfit_id"), f.get("look_id"), f.get("product_id"), f.get("reason")) for f in t.t["ig_feedback"]]
    assert events == [("approve", oid, look_id, None, None), ("hide", oid, look_id, None, "판매자 요청"),
                      ("hide", None, None, pid, "품절")]
    shown = C.attach_looks([io.get_outfit(oid)], d)[0]["look"]
    assert shown["items"][1]["pick"]["hidden_reason"] == "품절"                             # 화면: 내림 표시


@needs_ffmpeg
def test_remake_after_swap_refetches_coupang_image(coordi):
    t = coordi.t
    d = _deps(t)
    job = C.start("chaei", BOSE, "fill", d=d)
    C.run(job["id"], llm=FILL_LLM, rng=random.Random(2))
    oid = C.get_job(job["id"])["outfit_id"]
    for r in coordi.rest_out.rows:                                                         # 가짜 저장소 시각 → 실제처럼 tz 포함
        r["created_at"] = "2026-10-26T03:00:00+00:00"
    look = t.t["ig_looks"][0]
    K.swap(look["id"], 1, look["items"][1]["backups"][0]["id"], d=d)                       # 하의 c4 → c5
    rj = C.remake(oid, d=d)
    C.run_remake(rj["id"], rng=random.Random(5))
    j = C.get_job(rj["id"])
    assert j["state"] == "done" and j["outfit_id"] != oid
    new = next(r for r in coordi.rest_out.rows if r["id"] == j["outfit_id"])
    assert new["look_id"] == look["id"] and new["product_images"][1]["key"] == "insta/products/coupang/c5.jpg"
    assert not [k for k in coordi.s3.objs if k.startswith("insta/products/coupang/")]      # 다시 받아 쓰고 또 지움
    assert [f["event"] for f in t.t["ig_feedback"]] == ["swap"]


@needs_ffmpeg
def test_api_coordi_routes(coordi, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import insta as routes

    app = FastAPI()
    app.include_router(routes.router, prefix="/insta")
    c = TestClient(app)
    assert c.post("/insta/coordi", json={"products": [{**BOSE[0], "link": "http://x"}]}).status_code == 400
    r = c.post("/insta/coordi", json={"character_id": "chaei", "products": BOSE, "mode": "only"})
    assert r.status_code == 200
    j = c.get(f"/insta/coordi/jobs/{r.json()['id']}").json()
    assert j["state"] == "done" and j["cost"]["krw"] > 0
    lst = c.get("/insta/outfits", params={"character_id": "chaei"}).json()["outfits"]
    assert lst[0]["look"]["items"][0]["pick"]["mall"] == "무신사"
    oid = lst[0]["id"]
    assert c.post(f"/insta/outfits/{oid}/decision", json={"decision": "rejected"}).json()["decision"] == "rejected"
    assert c.post(f"/insta/outfits/{oid}/hide", json={"reason": ""}).status_code == 400
    assert c.post(f"/insta/outfits/{oid}/hide", json={"reason": "판매자 요청"}).status_code == 200
    assert c.get("/insta/outfits", params={"character_id": "chaei"}).json()["outfits"] == []
    assert c.get("/insta/coordi/jobs/cj_nope").status_code == 404
    assert c.post("/insta/coordi", json={"products": BOSE, "mode": "fill"}).status_code == 400   # 쿠팡 키 없음


# ── 오늘의 코디 찾기(완전 자동) ─────────────────────────────────────────────
AUTO_LOOK = {"concept": "가을 출근룩", "seasons": ["autumn"], "items": [
    {"kind": "bottoms", "color_name": "차콜", "hex": "#36454F", "fit": "regular", "queries": ["차콜 슬랙스 여성"]},
    {"kind": "shoes", "color_name": "블랙", "hex": "#111111", "queries": ["블랙 로퍼 여성"]},
]}


@needs_ffmpeg
def test_auto_ref_to_outfit_without_input(coordi):
    t = coordi.t
    t.t["ig_refs"] += [{"video_id": "m", "status": "analyzed", "views": 99, "analysis": {"usable": False, "looks": [AUTO_LOOK]}},
                       {"video_id": "v1", "status": "analyzed", "views": 10, "analysis": {"looks": [AUTO_LOOK]}}]
    d = _deps(t)
    job = C.start_auto("chaei", d=d)
    assert C.start_auto("chaei", d=d)["id"] == job["id"]                                   # 도는 중이면 같은 잡
    assert job["ref"] == "v1" and job["concept"] == "가을 출근룩"                          # '참고 안 함'은 건너뜀
    C.run_auto(job["id"], rng=random.Random(2))
    j = C.get_job(job["id"])
    assert j["state"] == "done" and j["outfit_id"], j
    look = t.t["ig_looks"][0]
    assert look["source"] == "reference" and look["status"] == "picked"
    assert [(it["kind"], it["source"]) for it in look["items"]] == [("bottoms", "coupang"), ("shoes", "coupang")]
    row = next(r for r in coordi.rest_out.rows if r["id"] == j["outfit_id"])
    assert row["look_id"] == look["id"] and [p["kind"] for p in row["product_images"]] == ["bottoms", "shoes"]
    assert t.t["ig_refs"][1]["status"] == "used"
    assert not [k for k in coordi.s3.objs if k.startswith("insta/products/coupang/")]      # 쿠팡 사본 삭제


def test_auto_needs_refs_and_coupang(coordi):
    with pytest.raises(C.CoordiError, match="레퍼런스"):
        C.start_auto("chaei", d=_deps(coordi.t))

    class _Off:
        def is_available(self):
            return False
    with pytest.raises(C.CoordiError, match="쿠팡"):
        C.start_auto("chaei", d=K.Deps(coupang=_Off(), vision=_vision(SCORES), download=_dl, rest=coordi.t))


def test_cap_products_keeps_clothes_first():
    ps = [{"kind": k} for k in ("bag", "accessory", "shoes", "outerwear", "top", "bottoms")]
    assert [p["kind"] for p in C._cap_products(ps)] == ["top", "bottoms", "outerwear", "shoes"]
