"""A3 — 컬렉션 릴스: 테마(AI·기본) · 옷 교체 프롬프트 · 영상 렌더 · 전체 흐름(가짜 쿠팡·비전·Muse·저장소)."""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import insta_collection as CL  # noqa: E402
from services import insta_picks as K  # noqa: E402
from test_insta_coordi import coordi  # noqa: E402,F401
from test_character_studio import studio  # noqa: E402,F401
from test_insta_outfit import flow  # noqa: E402,F401
from test_insta_picks import _c, _dl, _Shop, _vision  # noqa: E402
from test_shorts_cast import env  # noqa: E402,F401

_REAL_MIX = CL.BR.mix_queries


@pytest.fixture(autouse=True)
def _plain_queries(monkeypatch):
    """가짜 쇼핑은 검색어 그대로 매칭 — 브랜드 섞기는 따로 테스트."""
    monkeypatch.setattr(CL.BR, "mix_queries", lambda kind, qs, rng=None: list(qs)[:3])


needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 필요")
DEJAVU = ["/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def test_plan_theme_ai_and_fallback():
    def llm(s, u):
        assert "style_guide" in json.loads(u)
        return json.dumps({"kind": "outerwear", "concept": "레더 자켓", "title_en": "leather collection",
                           "title_ko": ["가을엔 역시", "레더 자켓"], "zip": "레더 자켓 모음.zip",
                           "queries": ["여성 레더 자켓", "여성 크롭 레더"], "base": [{"kind": "bottoms", "queries": ["여성 미니스커트"]},
                                                                               {"kind": "outerwear", "queries": ["x"]}]})
    t = CL.plan_theme("autumn", "주말", llm=llm)
    assert t["source"] == "ai" and t["title_en"] == "LEATHER COLLECTION" and [b["kind"] for b in t["base"]] == ["bottoms"]
    f = CL.plan_theme("autumn", "주말", recent=["퍼 아우터"], llm=lambda s, u: (_ for _ in ()).throw(RuntimeError("x")))
    assert f["source"] == "fallback" and f["concept"] == "앙고라 가디건"


@needs_ffmpeg
def test_render_reel(tmp_path, monkeypatch):
    if not all(Path(f).exists() for f in DEJAVU):
        pytest.skip("DejaVu 폰트 없음")
    monkeypatch.setattr(CL, "_SERIF", [DEJAVU[0]])
    monkeypatch.setattr(CL, "_BOLD", [DEJAVU[1]])
    for i in range(3):
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x{i}0{i}0{i}0:s=720x1280", "-frames:v", "1",
                        str(tmp_path / f"p{i}.jpg")], capture_output=True, check=True)
    theme = {"title_en": "FUR OUTER COLLECTION", "title_ko": ["추워지기 전에", "쟁여둘 퍼 아우터"], "zip": "퍼 아우터 모음.zip"}
    video, cover = CL.render_reel(tmp_path, ["p0.jpg", "p1.jpg", "p2.jpg"], theme)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(tmp_path / video)], capture_output=True, text=True).stdout)
    assert abs(dur - (CL.COVER_SEC + 3 * CL.LOOK_SEC)) < 0.3 and (tmp_path / cover).exists()
    w, h = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                           "-of", "csv=p=0", str(tmp_path / video)], capture_output=True, text=True).stdout.strip().split(",")
    assert (int(w), int(h)) == (CL.W, CL.H)


@needs_ffmpeg
def test_collection_end_to_end(coordi, monkeypatch):  # noqa: F811
    if not all(Path(f).exists() for f in DEJAVU):
        pytest.skip("DejaVu 폰트 없음")
    monkeypatch.setattr(CL, "_SERIF", [DEJAVU[0]])
    monkeypatch.setattr(CL, "_BOLD", [DEJAVU[1]])
    t = coordi.t
    t.t["ig_collections"] = []
    theme = dict(CL.FALLBACK_THEMES["autumn"][0])
    monkeypatch.setattr(CL, "plan_theme", lambda *a, **k: {**theme, "source": "fallback"})
    furs = [_c(f"f{i}", f"여성 퍼 자켓 {i}", price=69000, ch="coupang") for i in range(6)]
    shop = _Shop("coupang", {"여성 퍼 자켓": furs, "여성 블랙 미니스커트": [_c("sk", "여성 블랙 미니스커트", ch="coupang")],
                             "여성 블랙 롱부츠": [_c("bt", "여성 블랙 롱부츠", price=59000, ch="coupang")]})
    hexes = ["#F2EDE3", "#3B2A20", "#808080", "#111111", "#C8A27A", "#F2EDE3"]
    scores = {f"coupang_f{i}": (9 - i * 0.2, hexes[i]) for i in range(6)} | {"coupang_sk": (9, "#111111"),
                                                                             "coupang_bt": (9, "#111111")}
    d = K.Deps(coupang=shop, vision=_vision(scores), download=_dl, rest=t)
    job = CL.start("chaei", n=4, d=d)
    assert CL.start("chaei", n=4, d=d)["id"] == job["id"]
    CL.run(job["id"], rng=random.Random(3))
    j = CL.get_job(job["id"])
    assert j["state"] == "done", j
    row = t.t["ig_collections"][0]
    assert row["status"] == "ok" and len(row["looks"]) == 4 and row["video_key"].endswith("reel.mp4")
    assert [lk["n"] for lk in row["looks"]] == [1, 2, 3, 4]
    assert len({lk["product"]["id"] for lk in row["looks"]}) == 4                         # 룩마다 다른 상품
    calls = coordi.muse.calls
    assert len(calls) >= 4 and all("reference image 1" in c.prompt for c in calls), [c.prompt[:200] for c in calls if "reference image 1" not in c.prompt]
    scenes = [(lk["scene"]["pose"], lk["scene"]["location"]) for lk in row["looks"]]
    assert len({p for p, _ in scenes}) == 4 and len({loc for _, loc in scenes}) == 4       # 포즈·장소 모두 다름
    assert all(lk["items"] for lk in row["looks"])                                         # 함께 입는 옷도 룩마다
    assert row["video_key"] in coordi.s3.objs and row["cover_key"] in coordi.s3.objs
    assert not [k for k in coordi.s3.objs if k.startswith("insta/products/coupang/")]   # 쿠팡 사본 삭제
    shown = CL.list_collections(d=d)[0]
    assert shown["video_url"].endswith("reel.mp4") and shown["looks"][0]["image_url"]


@needs_ffmpeg
def test_plan_then_make(coordi, monkeypatch):  # noqa: F811
    """미리보기(테마·장면·상품, 이미지 생성 없음) → 확인 후 만들기."""
    if not all(Path(f).exists() for f in DEJAVU):
        pytest.skip("DejaVu 폰트 없음")
    monkeypatch.setattr(CL, "_SERIF", [DEJAVU[0]])
    monkeypatch.setattr(CL, "_BOLD", [DEJAVU[1]])
    t = coordi.t
    t.t["ig_collections"] = []
    theme = dict(CL.FALLBACK_THEMES["autumn"][0])
    monkeypatch.setattr(CL, "plan_theme", lambda *a, **k: {**theme, "source": "fallback"})
    furs = [_c(f"f{i}", f"여성 퍼 자켓 {i}", price=69000, ch="coupang") for i in range(5)]
    shop = _Shop("coupang", {"여성 퍼 자켓": furs, "여성 블랙 미니스커트": [_c("sk", "여성 블랙 미니스커트", ch="coupang")],
                             "여성 블랙 롱부츠": [_c("bt", "여성 블랙 롱부츠", price=59000, ch="coupang")]})
    hexes = ["#F2EDE3", "#3B2A20", "#808080", "#111111", "#C8A27A"]
    scores = {f"coupang_f{i}": (9 - i * 0.2, hexes[i]) for i in range(5)} | {"coupang_sk": (9, "#111111"), "coupang_bt": (9, "#111111")}
    d = K.Deps(coupang=shop, vision=_vision(scores), download=_dl, rest=t)
    j = CL.start_plan("chaei", n=3, d=d)
    CL.run(j["id"], rng=random.Random(1))
    assert CL.get_job(j["id"])["state"] == "done"
    row = t.t["ig_collections"][0]
    assert row["status"] == "planned" and row["theme"]["plan"]["mode"] == "varied"
    assert len([x for x in row["looks"] if not x.get("spare")]) == 4 and [x for x in row["looks"] if x.get("spare")]  # 최소 4 + 예비
    assert all(lk["scene"]["pose_ko"] and lk["scene"]["location_ko"] for lk in row["looks"])   # 미리보기에 장면
    assert all(lk["product"]["image_url"] for lk in row["looks"]) and all(len(lk["items"]) == 2 for lk in row["looks"])
    assert not coordi.muse.calls                                                          # 미리보기는 이미지 생성 없음
    assert not [k for k in coordi.s3.objs if k.startswith("insta/products/coupang/")]   # 사본 삭제
    shown = CL.list_collections(d=d)[0]
    assert shown["looks"][0]["product_image"]
    with pytest.raises(CL.CollectionError):
        t.t["ig_collections"].append({"id": "cl-20261027-aaaa", "character_id": "chaei", "status": "ok", "theme": {}})
        CL.start_make("cl-20261027-aaaa", d=d)
    m = CL.start_make(row["id"], d=d)
    CL.run(m["id"], rng=random.Random(1))
    assert CL.get_job(m["id"])["state"] == "done", CL.get_job(m["id"])
    row = next(r for r in t.t["ig_collections"] if r["id"] == row["id"])
    assert row["status"] == "ok" and row["video_key"] and len(row["looks"]) == 4
    assert len(coordi.muse.calls) >= 3 and all(lk.get("outfit_id") for lk in row["looks"])


def test_pick_variants_uses_all_queries(coordi):  # noqa: F811
    """코디는 검색어 1개만 쓰지만 컬렉션은 5개가 필요해 3개를 다 쓴다(1개만 쓰면 3개 미만으로 실패했음)."""
    t = coordi.t
    theme = dict(CL.FALLBACK_THEMES["autumn"][0])
    q = theme["queries"]
    items = {q[i]: [_c(f"q{i}{k}", f"{q[i]} {k}", price=69000, ch="coupang") for k in range(2)] for i in range(3)}
    hexes = ["#F2EDE3", "#3B2A20", "#808080", "#111111", "#C8A27A", "#2E4A7A"]
    scores = {f"coupang_q{i}{k}": (9, hexes[i * 2 + k]) for i in range(3) for k in range(2)}
    shop = _Shop("coupang", items)
    d = K.Deps(coupang=shop, vision=_vision(scores), download=_dl, rest=t)
    usage: dict = {}
    got = CL.pick_variants(theme, d, usage, n=5)
    assert shop.calls == q[:3] and len(got) == 5


def test_pick_variants_stops_on_quota(coordi):  # noqa: F811
    theme = dict(CL.FALLBACK_THEMES["autumn"][0])
    shop = _Shop("coupang", "quota")
    d = K.Deps(coupang=shop, vision=_vision({}), download=_dl, rest=coordi.t)
    usage: dict = {}
    assert CL.pick_variants(theme, d, usage) == [] and len(shop.calls) == 1
    assert any("한도" in n for n in usage["notes"])


def test_material_and_brand_mix():
    from services import insta_brands as BR
    assert CL.material_of("여성 크롭 레더 자켓") == "leather" and CL.material_of("지퍼 크롭 니트") == "knit"
    assert CL.material_of("겨울 오버핏 블루종") == "other"            # '겨울'은 울이 아님
    qs = _REAL_MIX("outerwear", ["a", "b", "c"], random.Random(1))
    assert qs[0].endswith(" a") and qs[0].split(" a")[0] in BR.brands("A", "outerwear")
    assert qs[1].endswith(" b") and qs[1].split(" b")[0] in BR.brands("B", "outerwear") and qs[2] == "c"
    assert _REAL_MIX("accessory", ["a"]) == ["a"]
    assert BR.excluded("마인 울코트") and not BR.excluded("마인드 니트") and BR.excluded("구찌 스타일 가방")
    assert BR.too_cheap_for_brand("나이키 에어포스", 39000, "shoes") and not BR.too_cheap_for_brand("나이키 에어포스", 99000, "shoes")


def test_pick_variants_avoids_same_color_and_material(coordi):  # noqa: F811
    """블랙 레더 3벌이 점수가 높아도 색·소재가 다른 것부터."""
    theme = dict(CL.FALLBACK_THEMES["autumn"][0])
    q = theme["queries"]
    names = ["여성 레더 자켓 A", "여성 레더 자켓 B", "여성 레더 자켓 C", "여성 스웨이드 자켓", "여성 울코트 브라운"]
    items = {q[0]: [_c(f"v{i}", nm, price=89000, ch="coupang") for i, nm in enumerate(names)]}
    hexes = ["#111111", "#121212", "#101010", "#8B5A2B", "#C8A27A"]
    scores = {f"coupang_v{i}": (9.5 - i * 0.1, hexes[i]) for i in range(5)}
    d = K.Deps(coupang=_Shop("coupang", items), vision=_vision(scores), download=_dl, rest=coordi.t)
    got = CL.pick_variants(theme, d, {}, n=3)
    assert [g["product_id"] for g in got] == ["v0", "v3", "v4"]


def test_base_specs_complete_outfit_for_miniskirt():
    """미니스커트(하의) 테마 가을 → 상의·아우터·신발까지(대표 2026-10-27: 롱부츠만 붙었음)."""
    theme = {"kind": "bottoms", "concept": "미니스커트", "queries": ["여성 데님 미니스커트"],
             "base": [{"kind": "shoes", "queries": ["여성 블랙 롱부츠"]}]}
    seen = {}

    def llm(system, user):
        seen["user"] = user
        return json.dumps({"concept": "x", "items": [
            {"kind": "top", "color_name": "아이보리", "hex": "#F2EDE3", "queries": ["여성 아이보리 크롭 니트"]},
            {"kind": "outerwear", "color_name": "브라운", "hex": "#5C4033", "queries": ["여성 브라운 스웨이드 자켓"]}]})
    specs = CL.base_specs(theme, "autumn", llm=llm)
    assert [s["kind"] for s in specs] == ["top", "outerwear", "shoes"]
    assert "미니스커트" in seen["user"]
    assert specs[2]["queries"][0] == "여성 블랙 롱부츠" and specs[0]["queries"][0] == "여성 아이보리 크롭 니트"


def test_pair_outfits_prefers_color_harmony_and_variety():
    def it(pid, hexv):
        return {"id": pid, "scores": {"hex": hexv}}
    variants = [it("v1", "#D7263D"), it("v2", "#111111")]                 # 빨강 스커트 / 블랙 스커트
    tops = [it("t_green", "#1FA84F"), it("t_ivory", "#F2EDE3"), it("t_grey", "#808080")]
    out = CL.pair_outfits(variants, [tops])
    assert out[0][1]["id"] in ("t_ivory", "t_grey")                       # 빨강+초록(포인트 2개)은 피함
    assert out[0][1]["id"] != out[1][1]["id"]                           # 룩마다 다른 상의


def test_plan_retries_with_new_theme_when_products_short(coordi, monkeypatch):  # noqa: F811
    """첫 테마 상품이 모자라면 테마를 바꿔 다시(대표 2026-10-27: 실패하면 스스로)."""
    t = coordi.t
    t.t["ig_collections"] = []
    themes = iter([{**CL.FALLBACK_THEMES["autumn"][0], "concept": "없는테마", "queries": ["없음1", "없음2", "없음3"]},
                   dict(CL.FALLBACK_THEMES["autumn"][0])])
    seen_avoid = []

    def fake_theme(season, life, recent=None, **k):
        seen_avoid.append(list(recent or []))
        return {**next(themes), "source": "fallback"}
    monkeypatch.setattr(CL, "plan_theme", fake_theme)
    furs = [_c(f"f{i}", f"여성 퍼 자켓 {i}", price=69000, ch="coupang") for i in range(4)]
    hexes = ["#F2EDE3", "#3B2A20", "#808080", "#111111"]
    shop = _Shop("coupang", {"여성 퍼 자켓": furs})
    d = K.Deps(coupang=shop, vision=_vision({f"coupang_f{i}": (9, hexes[i]) for i in range(4)}), download=_dl, rest=t)
    j = CL.start_plan("chaei", n=3, d=d)
    CL.run(j["id"], rng=random.Random(2))
    assert CL.get_job(j["id"])["state"] == "done", CL.get_job(j["id"])
    row = t.t["ig_collections"][0]
    assert row["status"] == "planned" and row["usage"]["themes_tried"] == ["없는테마", "퍼 아우터"]
    assert "없는테마" in seen_avoid[1]                                       # 실패한 테마는 다시 안 고름
    assert "여성 없는테마" in shop.calls                                     # 넓은 검색어로도 한 번 더 찾음


def test_broaden_queries():
    assert CL.broaden_queries({"kind": "bottoms", "concept": "미니스커트 모음", "queries": []}) == ["여성 미니스커트"]
    assert CL.broaden_queries({"kind": "outerwear", "concept": "앙고라 가디건", "queries": []}) == ["여성 앙고라 가디건", "여성 가디건"]


def test_concept_match_rejects_other_items():
    """'앙고라 가디건' 테마에 후드 집업·자켓이 섞이던 문제(2026-10-28)."""
    t = {"concept": "앙고라 가디건", "kind": "outerwear"}
    assert not CL.concept_match("여 헤어리 후드 집업", t) and not CL.concept_match("키르시 코튼 자켓", t)
    assert CL.concept_match("여성 앙고라 니트 가디건", t) and CL.concept_match("헤어리 루즈핏 가디건", t)
    assert CL.concept_match("빈티지 퍼 카라 자켓", {"concept": "퍼 아우터"})          # 아우터 = 자켓 등
    assert CL.concept_match("카고 미니 스커트", {"concept": "미니스커트"})


def test_lookfirst_plan_designs_looks_then_finds_products(coordi, monkeypatch):  # noqa: F811
    """룩 먼저 설계 → 쿠팡에서 아이템별 1등(엄격) → 옷이 없으면 그 룩은 버림 → 흰 스튜디오 전신 장면."""
    t = coordi.t
    t.t["ig_collections"] = []
    looks = []
    items = {}
    scores = {}
    for k in range(6):
        q_top, q_bot, q_shoe = f"여성 상의{k}", f"여성 하의{k}", f"여성 신발{k}"
        looks.append({"idea": f"룩{k}", "items": [
            {"kind": "top", "color_name": "아이보리", "hex": "#F2EDE3", "queries": [q_top]},
            {"kind": "bottoms", "color_name": "블랙", "hex": "#111111", "queries": [q_bot]},
            {"kind": "shoes", "color_name": "블랙", "hex": "#111111", "queries": [q_shoe]}]})
        if k != 2:   # 룩2는 상의를 못 찾음 → 버림
            items[q_top] = [_c(f"t{k}", f"여성 니트 {k}", price=59000, ch="coupang")]
            scores[f"coupang_t{k}"] = (9, "#F2EDE3")
        items[q_bot] = [_c(f"b{k}", f"여성 스커트 {k}", price=49000, ch="coupang")]
        items[q_shoe] = [_c(f"s{k}", f"여성 부츠 {k}", price=79000, ch="coupang")]
        scores |= {f"coupang_b{k}": (9, "#111111"), f"coupang_s{k}": (9, "#111111")}
    design = {"concept": "가을 룩북", "title_en": "AUTUMN LOOKBOOK", "zip": "가을 룩북.zip", "looks": looks}
    d = K.Deps(coupang=_Shop("coupang", items), vision=_vision(scores), download=_dl, rest=t)
    j = CL.start_plan("chaei", n=4, d=d, mode="lookfirst")
    with CL._LOCK:
        CL._JOBS[j["id"]]["_args"]["look_llm"] = lambda s, u: json.dumps(design)
    CL.run(j["id"], rng=random.Random(1))
    assert CL.get_job(j["id"])["state"] == "done", CL.get_job(j["id"])
    row = t.t["ig_collections"][0]
    main = [x for x in row["looks"] if not x.get("spare")]
    assert row["theme"]["plan"]["mode"] == "lookfirst" and len(main) == 4
    assert all(x["scene"]["location"] == "white_studio" and x["scene"]["pose"] == "studio_full_body" for x in main)
    assert "룩2" in row["usage"]["dropped"] and all(x["idea"] != "룩2" for x in row["looks"])
    assert [x["product"]["kind"] for x in main] == ["top"] * 4 and all(len(x["items"]) == 2 for x in main)
    assert not [k for k in coordi.s3.objs if k.startswith("insta/products/coupang/")]


def test_stale_jobs_after_restart_are_marked_failed(coordi):  # noqa: F811
    """재배포로 메모리 잡이 사라져 making/빈 planned 로 남은 행 → 목록을 열 때 실패로 정리(2026-10-28)."""
    from datetime import datetime, timedelta, timezone
    t = coordi.t
    old = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    fresh = datetime.now(timezone.utc).isoformat()
    t.t["ig_collections"] = [
        {"id": "cl-20261028-aaaa", "character_id": "chaei", "status": "making", "theme": {"plan": {}}, "looks": [],
         "created_at": old, "updated_at": old},
        {"id": "cl-20261028-bbbb", "character_id": "chaei", "status": "planned", "theme": {}, "looks": [],
         "created_at": old, "updated_at": old},
        {"id": "cl-20261028-cccc", "character_id": "chaei", "status": "making", "theme": {"plan": {}}, "looks": [],
         "created_at": fresh, "updated_at": fresh},
        {"id": "cl-20261028-dddd", "character_id": "chaei", "status": "planned", "theme": {"plan": {"mode": "varied"}},
         "looks": [], "created_at": old, "updated_at": old},
    ]
    d = K.Deps(coupang=_Shop("coupang", {}), vision=_vision({}), download=_dl, rest=t)
    rows = {r["id"]: r for r in CL.list_collections(d=d)}
    assert rows["cl-20261028-aaaa"]["status"] == "failed" and rows["cl-20261028-bbbb"]["status"] == "failed"
    assert rows["cl-20261028-cccc"]["status"] == "making"                  # 방금 시작한 건 그대로
    assert rows["cl-20261028-dddd"]["status"] == "planned"                 # 기획 끝난 미리보기는 그대로
    assert rows["cl-20261028-aaaa"]["error"] == CL.STALE_MSG
