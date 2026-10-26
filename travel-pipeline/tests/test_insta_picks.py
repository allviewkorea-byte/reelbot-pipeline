"""A2-2 — 쿠팡·네이버 픽: 서명·파싱·한도 · 1차 필터(키즈·남성·세트·중복·가격) · 색 조합 · 쿠팡 우선 · 전체 흐름."""

from __future__ import annotations

import hashlib
import hmac
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters import shopping as S  # noqa: E402
from services import insta_picks as K  # noqa: E402
from services import insta_refs as R  # noqa: E402
from test_shorts_cast import env  # noqa: E402,F401

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 필요")


# ── 어댑터 ───────────────────────────────────────────────────────────────
def test_coupang_sign():
    now = datetime(2026, 10, 26, 1, 2, 3, tzinfo=timezone.utc)
    signed, sig = S.coupang_sign("GET", S.COUPANG_SEARCH, "keyword=a&limit=10", "sec", now)
    assert signed == "261026T010203Z"
    assert sig == hmac.new(b"sec", f"{signed}GET{S.COUPANG_SEARCH}keyword=a&limit=10".encode(), hashlib.sha256).hexdigest()


def test_coupang_search_cap_and_deeplink():
    calls = []

    def http(method, url, headers, body):
        calls.append((method, url, headers, body))
        if method == "POST":
            return {"data": [{"originalUrl": u, "shortenUrl": "https://link.coupang.com/a/x"} for u in body["coupangUrls"]]}
        return {"data": {"productData": [{"productId": 7, "productName": "여성 니트 &amp; 가디건", "productPrice": 29000,
                                          "productImage": "https://img/7.jpg", "productUrl": "https://link.coupang.com/re/AFF",
                                          "categoryName": "여성패션", "isRocket": True}, {"productId": 8}]}}

    c = S.CoupangClient("ak", "sk", http=http)
    got = c.search("니트", 30)
    assert got[0]["name"] == "여성 니트 & 가디건" and got[0]["mall"] == "쿠팡 로켓" and len(got) == 1   # 이미지 없는 건 제외
    assert "limit=10" in calls[0][1] and calls[0][2]["Authorization"].startswith("CEA algorithm=HmacSHA256, access-key=ak, signed-date=")
    for _ in range(S.COUPANG_SEARCH_HOURLY_CAP - 1):
        c.search("x")
    with pytest.raises(S.QuotaExceeded):
        c.search("x")
    links = c.deeplinks(["https://link.coupang.com/re/AFF", "https://www.coupang.com/vp/products/1"])
    assert links["https://link.coupang.com/re/AFF"] == "https://link.coupang.com/re/AFF"
    assert links["https://www.coupang.com/vp/products/1"] == "https://link.coupang.com/a/x"
    assert not S.CoupangClient("", "").is_available()


def test_naver_parse():
    def http(url, params, headers):
        assert headers["X-Naver-Client-Id"] == "id" and params["sort"] == "sim"
        return {"items": [{"title": "<b>베이지</b> 울 코트", "link": "https://smartstore/1", "image": "https://i/1.jpg", "lprice": "89000",
                           "mallName": "몰A", "productId": "11", "category1": "패션의류", "category2": "여성의류"}]}
    got = S.NaverClient("id", "sec", http=http).search("코트")
    assert got[0]["name"] == "베이지 울 코트" and got[0]["price"] == 89000 and got[0]["category"] == "패션의류 > 여성의류"


# ── 필터·조합 ────────────────────────────────────────────────────────────
def _c(pid, name, price=30000, img=None, cat="여성의류", ch="naver"):
    return {"channel": ch, "product_id": pid, "name": name, "price": price, "image_url": img or f"https://i/{pid}.jpg", "category": cat}


def test_code_filter():
    cands = [_c("1", "여성 울 니트"), _c("2", "키즈 니트"), _c("3", "남성 니트"), _c("4", "니트 2종 세트"), _c("5", "니트 1+1"),
             _c("6", "여성 니트", cat="남성의류"), _c("7", "여성 울 니트 [무료배송]"), _c("8", "다른 니트", img="https://i/1.jpg?x=1"),
             _c("9", "고가 니트", price=900000), _c("10", "아주 싼 니트", price=1000)]
    kept, why = K.code_filter(cands, "top")
    assert [c["product_id"] for c in kept] == ["1"]
    assert why == {"price": 2, "excluded": 5, "duplicate": 2}


def test_color_family_and_combo():
    assert K.color_family("#111111") == ("black", False) and K.color_family("#F5F0E6")[0] in ("white", "beige")
    assert K.color_family("#D2B48C") == ("beige", False) and K.color_family("#1F2A44") == ("navy", False)
    assert K.color_family("#E02020") == ("red", True) and K.color_family("bad") == ("unknown", False)
    assert K.combo_violations(["#111111", "#D2B48C", "#E02020"])["ok"]
    bad = K.combo_violations(["#E02020", "#2050E0", "#111111"])
    assert not bad["ok"] and "포인트색 2개" in bad["reason"]
    assert not K.combo_violations(["#111111", "#FFFFFF", "#D2B48C", "#E02020", "#1F2A44"])["ok"]


def test_fix_combo_swaps_to_backup():
    items = [
        {"index": 0, "pick": {"product_id": "a", "score": 90, "scores": {"hex": "#E02020"}}, "backups": []},
        {"index": 1, "pick": {"product_id": "b", "score": 80, "scores": {"hex": "#2050E0"}},
         "backups": [{"product_id": "b2", "score": 78, "scores": {"hex": "#111111"}}]},
    ]
    res = K.fix_combo(items, lambda c: c["scores"]["hex"])
    assert res["ok"] and items[1]["pick"]["product_id"] == "b2" and res["swaps"][0]["from"] == "b"
    assert items[1]["backups"][-1]["product_id"] == "b"


def test_choose_prefers_coupang_within_margin():
    s = [{"channel": "naver", "score": 90, "product_id": "n"}, {"channel": "coupang", "score": 86, "product_id": "c"},
         {"channel": "naver", "score": 70, "product_id": "n2"}, {"channel": "naver", "score": 50, "product_id": "low"}]
    pick, backups, miss = K.choose(s)
    assert pick["product_id"] == "c" and [b["product_id"] for b in backups] == ["n", "n2"] and miss is None
    pick, _, _ = K.choose([{"channel": "naver", "score": 90, "product_id": "n"}, {"channel": "coupang", "score": 80, "product_id": "c"}])
    assert pick["product_id"] == "n"
    pick, backups, miss = K.choose([{"channel": "naver", "score": 40, "product_id": "x"}])
    assert pick is None and miss


def test_total_score_and_season_penalty():
    full = {"kind": 10, "color": 10, "fit": 10, "length": 10, "details": 10}
    assert K.total_score(full) == 100 and K.total_score(full, season_ok=False) == 80
    assert K.total_score({"kind": 10, "color": 0, "fit": 10, "length": 10, "details": 10}) == 70


# ── 전체 흐름 ────────────────────────────────────────────────────────────
class _Tables:
    def __init__(self):
        self.t = {"ig_refs": [], "ig_products": [], "ig_looks": [], "ig_api_usage": []}
        self.next_id = 1

    def _m(self, r, params):
        for k, v in params.items():
            if k in ("select", "order", "limit", "on_conflict"):
                continue
            if str(r.get(k)) != v.split(".", 1)[1]:
                return False
        return True

    def __call__(self, table, method, *, params=None, json_body=None, prefer=None):
        params, rows = params or {}, self.t[table]
        if method == "GET":
            return [dict(r) for r in rows if self._m(r, params)][: int(params.get("limit", 999))]
        if method == "POST":
            out = []
            keys = (params.get("on_conflict") or "").split(",")
            for rec in json_body:
                old = next((r for r in rows if keys != [""] and all(r.get(k) == rec.get(k) for k in keys)), None)
                if old:
                    old.update(rec)
                    out.append(dict(old))
                    continue
                row = {**rec}
                if table == "ig_products":
                    row["id"] = self.next_id
                    self.next_id += 1
                rows.append(row)
                out.append(dict(row))
            return out
        if method == "PATCH":
            for r in rows:
                if self._m(r, params):
                    r.update(json_body)
            return []
        raise AssertionError(method)


class _Shop:
    def __init__(self, name, items, ok=True):
        self.name, self.items, self.ok, self.calls = name, items, ok, []

    def is_available(self):
        return self.ok

    def search(self, q, n):
        self.calls.append(q)
        return [dict(i) for i in self.items.get(q, [])]

    def deeplinks(self, urls):
        return {u: f"https://link.coupang.com/a/{u[-1]}" for u in urls}


def _dl(url, dest):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=500x600", "-frames:v", "1", "-f", "image2",
                    "-c:v", "png", str(dest)], check=True)
    return dest


LOOK = {"concept": "가을 출근룩", "seasons": ["autumn"], "items": [
    {"kind": "top", "color_name": "아이보리", "hex": "#F2EDE3", "fit": "regular", "queries": ["아이보리 니트 여성", "울 니트 여성"]},
    {"kind": "bottoms", "color_name": "차콜", "hex": "#36454F", "fit": "regular", "queries": ["차콜 슬랙스 여성"]},
]}


def _setup(tables):
    tables.t["ig_refs"].append({"video_id": "v1", "status": "analyzed", "views": 10, "analysis": {"looks": [LOOK]}})
    cp = _Shop("coupang", {"아이보리 니트 여성": [_c("c1", "여성 아이보리 니트", ch="coupang") | {"link": "https://www.coupang.com/vp/1", "mall": "쿠팡"}]})
    nv = _Shop("naver", {
        "아이보리 니트 여성": [_c("n1", "아이보리 울 니트"), _c("n2", "키즈 니트")],
        "울 니트 여성": [_c("n3", "여성 울 라운드 니트")],
        "차콜 슬랙스 여성": [_c("n4", "차콜 와이드 슬랙스"), _c("n5", "레드 슬랙스"), _c("n6", "블랙 슬랙스")],
    })
    return cp, nv


def _vision(scores_by_name):
    def v(system, labeled, ask, task, max_tokens=1500):
        if task == "insta_pick_usable":
            return {"results": [{"n": i + 1, "usable": True} for i in range(len(labeled))]}
        names = [str(p) for _, p in labeled]
        res = []
        for i, path in enumerate(names):
            key = next((k for k in scores_by_name if k in path), None)
            sc, hexv = scores_by_name.get(key, (5, "#808080"))
            res.append({"n": i + 1, "kind": sc, "color": sc, "fit": sc, "length": sc, "details": sc, "hex": hexv, "season_ok": True})
        return {"results": res}
    return v


@needs_ffmpeg
def test_pick_look_end_to_end(env):  # noqa: F811
    t = _Tables()
    cp, nv = _setup(t)
    scores = {"coupang_c1": (8.7, "#F2EDE3"), "naver_n1": (9, "#F2EDE3"), "naver_n3": (7, "#EEE8DD"),
              "naver_n4": (9, "#36454F"), "naver_n5": (8, "#E02020"), "naver_n6": (7, "#111111")}
    d = K.Deps(coupang=cp, naver=nv, vision=_vision(scores), download=_dl, rest=t)
    import services.insta_refs as refs_mod
    orig = refs_mod.rest
    refs_mod.rest = t
    try:
        job = K.start(d=d)
        K.run(job["id"])
    finally:
        refs_mod.rest = orig
    j = K.get_job(job["id"])
    assert j["state"] == "done"
    look = t.t["ig_looks"][0]
    assert look["status"] == "picked" and look["concept"] == "가을 출근룩"
    top, bottom = look["items"]
    assert top["pick"]["channel"] == "coupang" and top["pick"]["product_id"] == "c1"      # 네이버 90 vs 쿠팡 87 → 쿠팡
    assert top["pick"]["affiliate_link"] == "https://link.coupang.com/a/1"                 # 쿠팡 딥링크
    assert top["filtered"]["excluded"] == 1 and "n2" not in [b["product_id"] for b in top["backups"]]
    assert bottom["pick"]["product_id"] == "n4" and [b["product_id"] for b in bottom["backups"]] == ["n5", "n6"]
    assert cp.calls == ["아이보리 니트 여성", "차콜 슬랙스 여성"]                           # 쿠팡은 아이템당 검색어 1개
    assert set(nv.calls) == {"아이보리 니트 여성", "울 니트 여성", "차콜 슬랙스 여성"}
    assert look["usage"] == {"coupang": 2, "naver": 3, "vision": 4}
    assert look["combo"]["ok"]
    prods = {p["product_id"]: p for p in t.t["ig_products"]}
    assert prods["c1"]["image_key"] == "insta/products/coupang/c1.jpg" and env.s3.objs["insta/products/coupang/c1.jpg"][0][:3] == b"\xff\xd8\xff"
    assert t.t["ig_refs"][0]["status"] == "used"
    assert {(u["api"], u["calls"]) for u in t.t["ig_api_usage"]} == {("coupang", 2), ("naver", 3)}


@needs_ffmpeg
def test_vision_failure_falls_back(env):  # noqa: F811
    t = _Tables()
    cp, nv = _setup(t)

    def boom(*a, **k):
        raise RuntimeError("anthropic down")

    d = K.Deps(coupang=_Shop("coupang", {}, ok=False), naver=nv, vision=boom, download=_dl, rest=t)
    job = K.start(d=d)
    K.run(job["id"])
    look = t.t["ig_looks"][0]
    top = look["items"][0]
    assert "쿠팡 연결 필요" in top["notes"] and any("AI 호출 실패" in n for n in top["notes"])
    assert top["pick"] and top["pick"]["scores"]["fallback"] is True


def test_start_errors():
    t = _Tables()
    no = _Shop("x", {}, ok=False)
    with pytest.raises(S.ShoppingError, match="연결"):
        K.start(d=K.Deps(coupang=no, naver=no, rest=t))
    with pytest.raises(S.ShoppingError, match="레퍼런스"):
        K.start(d=K.Deps(coupang=_Shop("c", {}), naver=no, rest=t))


def test_swap(env):  # noqa: F811
    t = _Tables()
    t.t["ig_looks"].append({"id": "lk-20261026-abcd", "items": [{"index": 0, "pick": {"id": 1, "product_id": "a"},
                                                                  "backups": [{"id": 2, "product_id": "b"}, {"id": 3, "product_id": "c"}]}]})
    out = K.swap("lk-20261026-abcd", 0, 3, d=K.Deps(coupang=_Shop("c", {}), naver=_Shop("n", {}), rest=t))
    it = out["items"][0]
    assert it["pick"]["id"] == 3 and [b["id"] for b in it["backups"]] == [2, 1]
    with pytest.raises(S.ShoppingError):
        K.swap("lk-20261026-abcd", 0, 99, d=K.Deps(coupang=_Shop("c", {}), naver=_Shop("n", {}), rest=t))
