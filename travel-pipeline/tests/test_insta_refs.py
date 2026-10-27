"""A2-1 — 캐릭터 치수 · 유튜브 레퍼런스 수집(쿼터 상한·중복 금지·검색어) · 룩 분석 정규화 · 하루 1회 실행.
A2-3a — 레퍼런스 필터(남성·명품 제외, 참고 안 함 저장) · 스크린샷 레퍼런스."""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import character_measurements as cm  # noqa: E402
from services import character_studio as cs  # noqa: E402
from services import insta_refs as R  # noqa: E402
from test_character_studio import studio  # noqa: E402,F401
from test_shorts_cast import env  # noqa: E402,F401

NOW = datetime(2026, 10, 26, 3, 0, tzinfo=timezone.utc)   # KST 월요일 12시, 가을
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 필요")


# ── 치수 ─────────────────────────────────────────────────────────────────
def test_measurements_draft_save_validate(studio):  # noqa: F811
    got = cm.get("chaei")
    assert got["draft"] and not got["saved"] and got["values"]["height"] == 172 and got["values"]["size_shoes"] == "240"
    assert cm.saved(cs.get_character("chaei")) is None                                  # 초안은 저장 아님
    with pytest.raises(cs.StudioError, match="허리둘레"):
        cm.save("chaei", {**cm.DRAFTS["chaei"], "waist": 300})
    with pytest.raises(cs.StudioError, match="숫자"):
        cm.save("chaei", {**cm.DRAFTS["chaei"], "chest": "abc"})
    out = cm.save("chaei", {**cm.DRAFTS["chaei"], "height": "171.5"})
    assert out["saved"] and out["values"]["height"] == 171.5
    ch = cs.get_character("chaei")
    assert cm.saved(ch)["hip"] == 91 and ch["channel_id"] == "insta_chaei"              # bible 다른 값·채널 유지
    cs.upsert_character("mina", "미나")
    assert cm.get("mina") == {"values": {}, "saved": False, "draft": False, "fields": cm.fields()}


def test_measurements_api(studio):  # noqa: F811
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import studio as routes

    app = FastAPI()
    app.include_router(routes.router, prefix="/studio")
    c = TestClient(app)
    assert c.get("/studio/characters/chaei/measurements").json()["draft"] is True
    assert c.post("/studio/characters/chaei/measurements", json={"values": {"height": 10}}).status_code == 400
    r = c.post("/studio/characters/chaei/measurements", json={"values": cm.DRAFTS["chaei"]})
    assert r.status_code == 200 and r.json()["saved"] is True


# ── 수집 ─────────────────────────────────────────────────────────────────
class _FakeTables:
    def __init__(self):
        self.t: dict[str, list[dict]] = {"ig_refs": [], "ig_api_usage": []}

    def _match(self, row, params):
        for k, v in params.items():
            if k in ("select", "order", "limit", "on_conflict"):
                continue
            op, _, val = v.partition(".")
            cur = str(row.get(k))
            if op == "eq" and cur != val:
                return False
            if op == "in" and cur not in val.strip("()").split(","):
                return False
        return True

    def __call__(self, table, method, *, params=None, json_body=None, prefer=None):
        params, rows = params or {}, self.t[table]
        if method == "GET":
            out = [dict(r) for r in rows if self._match(r, params)]
            return out[: int(params.get("limit", 999))]
        if method == "POST":
            keys = (params.get("on_conflict") or "").split(",")
            for rec in json_body:
                old = next((r for r in rows if keys != [""] and all(r.get(k) == rec.get(k) for k in keys)), None)
                if old and "ignore-duplicates" in (prefer or ""):
                    continue
                if old:
                    old.update(rec)
                else:
                    rows.append({"status": "new", "analysis": None, **rec})
            return []
        if method == "PATCH":
            for r in rows:
                if self._match(r, params):
                    r.update(json_body)
            return []
        raise AssertionError(method)


class _FakeYT:
    def __init__(self, ids_by_query):
        self.ids_by_query, self.calls = ids_by_query, []

    def __call__(self, url, params):
        self.calls.append((url.rsplit("/", 1)[1], params))
        if url.endswith("/search"):
            return {"items": [{"id": {"videoId": i}} for i in self.ids_by_query.get(params["q"].split(" -")[0], [])]}
        ids = params["id"].split(",")
        return {"items": [{"id": i, "snippet": {"title": f"{i} 가을 코디", "channelTitle": "ch", "description": "상의: 베이지 니트\n하의 - 와이드 슬랙스",
                                                 "publishedAt": "2026-10-20T00:00:00Z",
                                                 "thumbnails": {"high": {"url": f"https://i.ytimg.com/{i}.jpg"}}},
                           "statistics": {"viewCount": str(1000 * (n + 1))}} for n, i in enumerate(ids)]}


def _download(url, dest):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=640x360", "-frames:v", "1", str(dest)], check=True)
    return dest


@pytest.fixture
def refs_env(env, monkeypatch):  # noqa: F811
    t = _FakeTables()
    monkeypatch.setattr(R, "rest", t)
    monkeypatch.setenv("INSTA_YOUTUBE_API_KEY", "k")
    env.tables = t
    return env


def _llm(qs):
    return lambda s, u: '{"queries": %s}' % str(qs).replace("'", '"')


@needs_ffmpeg
def test_collect_saves_dedupes_and_counts_units(refs_env):
    yt = _FakeYT({"가을 코디": ["a1", "a2", "a3", "a4", "a5"], "출근룩": ["a1", "b1"]})
    out = R.collect(NOW, http_get=yt, llm=_llm(["가을 코디", "출근룩"]), download=_download)
    assert out["saved"] == 6 and out["units"] == 2 * (R.SEARCH_COST + R.VIDEOS_COST)
    rows = refs_env.tables.t["ig_refs"]
    # 첫 검색: 조회수 상위 4개(a2~a5)만 저장 → a1 은 두 번째 검색에서 새 영상으로 저장
    assert {r["video_id"] for r in rows} == {"a1", "a2", "a3", "a4", "a5", "b1"} and out["dupes"] == 0
    assert rows[0]["thumb_key"] == f"insta/refs/{rows[0]['video_id']}.jpg"
    q = next(p for name, p in yt.calls if name == "search")["q"]
    assert q.endswith(R.QUERY_EXCLUDE) and "-남자" in q and "-명품" in q                  # 남성·명품 영상은 검색에서 뺀다
    assert refs_env.s3.objs[rows[0]["thumb_key"]][0][:3] == b"\xff\xd8\xff"
    search = [p for k, p in yt.calls if k == "search"][0]
    assert search["order"] == "viewCount" and search["publishedAfter"].startswith("2026-09-26")
    u = R.usage("youtube", NOW)
    assert u["units"] == 202 and u["calls"] == 4 and u["cap"] == R.YT_DAILY_UNIT_CAP
    again = R.collect(NOW, http_get=yt, llm=_llm(["가을 코디"]), download=_download)
    assert again["saved"] == 0 and again["dupes"] == 5 and len(refs_env.tables.t["ig_refs"]) == 6   # 같은 영상 중복 금지


def test_collect_stops_at_quota(refs_env):
    refs_env.tables.t["ig_api_usage"].append({"day": "2026-10-26", "api": "youtube", "units": R.YT_DAILY_UNIT_CAP - 50, "calls": 5})
    yt = _FakeYT({"가을 코디": ["x"]})
    out = R.collect(NOW, http_get=yt, llm=_llm(["가을 코디"]), download=_download)
    assert out["stopped_by_quota"] and yt.calls == [] and out["saved"] == 0


def test_collect_without_key(refs_env, monkeypatch):
    monkeypatch.delenv("INSTA_YOUTUBE_API_KEY")
    monkeypatch.delenv("MUSIC_TREND_YOUTUBE_API_KEY", raising=False)
    monkeypatch.setenv("YOUTUBE_API_KEY", "upload-key")                                 # 업로드 키는 쓰지 않는다
    assert "키 없음" in R.collect(NOW, http_get=_FakeYT({}))["skipped"]


def test_query_choice_and_fallback():
    assert R.choose_queries(NOW, 2, _llm(["가을 코디", "가을 코디", "출근룩", "x"])) == ["가을 코디", "출근룩"]
    fb = R.choose_queries(NOW, 3, lambda s, u: (_ for _ in ()).throw(RuntimeError("down")))
    assert fb[0] == "가을 코디" and "출근룩" in fb                                        # 월요일 → 출근
    dec = R.fallback_queries(datetime(2026, 12, 10, 3, tzinfo=timezone.utc), 3)
    assert "크리스마스 데이트룩" in dec and dec[0] == "겨울 코디"


def test_product_lines():
    lines = R.product_lines("오늘 코디 소개\n상의: 아뜰리에 베이지 니트\n- shoes: 로퍼\n구독 좋아요\n" + "x" * 300)
    assert lines == ["상의: 아뜰리에 베이지 니트", "shoes: 로퍼"]


def test_normalize_analysis():
    raw = {"looks": [
        {"concept": "가을 출근 미니멀룩 아주 긴 이름", "seasons": ["autumn", "fall"], "items": [
            {"kind": "outerwear", "color_name": "카멜", "hex": "#C19A6B", "fit": "over", "queries": ["여성 카멜 울 코트", "카멜 롱코트"]},
            {"kind": "hat", "queries": ["모자"]},
            {"kind": "bottoms", "hex": "brown", "fit": "baggy", "queries": ["와이드 슬랙스", "와이드 슬랙스"]},
            {"kind": "shoes", "queries": []}]},
        {"concept": "빈 룩", "items": []}],
        "desc_products": [{"name": "울 코트", "brand": "A"}, {"brand": "no name"}]}
    spec = R.normalize_analysis(raw)
    assert len(spec["looks"]) == 1
    lk = spec["looks"][0]
    assert lk["concept"] == "가을 출근 미니멀룩 아주"[:12] and lk["seasons"] == ["autumn"]
    assert [i["kind"] for i in lk["items"]] == ["outerwear", "bottoms"]
    assert lk["items"][1]["hex"] is None and lk["items"][1]["fit"] == "regular" and lk["items"][1]["queries"] == ["와이드 슬랙스"]
    assert spec["desc_products"] == [{"name": "울 코트", "brand": "A", "kind": ""}]


@needs_ffmpeg
def test_run_once_a_day_and_analyze(refs_env):
    yt = _FakeYT({"가을 코디": ["v1", "v2"]})
    spec = {"looks": [{"concept": "가을 출근룩", "items": [{"kind": "top", "queries": ["베이지 니트 여성"]}]}]}
    calls = []

    def vision(system, images, ask, task, max_tokens=400):
        calls.append(ask)
        if "v2" in ask:
            return {"looks": []}
        return spec

    assert R.try_begin()
    out = R.run(now=NOW, http_get=yt, llm=_llm(["가을 코디"]), download=_download, vision=vision)
    assert out["collect"]["saved"] == 2 and out["analyzed"] == 1 and not R.status()["running"]
    rows = {r["video_id"]: r for r in refs_env.tables.t["ig_refs"]}
    assert rows["v1"]["status"] == "analyzed" and rows["v1"]["analysis"]["looks"][0]["concept"] == "가을 출근룩"
    assert rows["v2"]["status"] == "failed" and "룩" in rows["v2"]["error"]
    assert "상의" in calls[0]                                                          # 설명란 제품 줄 전달
    assert R.try_begin()
    again = R.run(now=NOW, http_get=yt, llm=_llm(["가을 코디"]), download=_download, vision=vision)
    assert again["collect"]["skipped"] and len([c for c in yt.calls if c[0] == "search"]) == 1   # 하루 1회
    assert R.try_begin() and not R.try_begin()                                           # 동시 실행 방지
    R._STATE["running"] = False


@needs_ffmpeg
def test_api_refs(refs_env):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import insta as routes

    refs_env.tables.t["ig_refs"].append({"video_id": "z1", "title": "t", "thumb_key": "insta/refs/z1.jpg", "status": "analyzed",
                                         "analysis": {"looks": []}, "collected_at": "2026-10-26"})
    app = FastAPI()
    app.include_router(routes.router, prefix="/insta")
    c = TestClient(app)
    got = c.get("/insta/refs").json()["refs"][0]
    assert got["thumb_url"] == "https://img.test/insta/refs/z1.jpg" and got["video_url"].endswith("v=z1")
    u = c.get("/insta/usage").json()
    assert u["youtube"]["cap"] == R.YT_DAILY_UNIT_CAP and u["has_youtube_key"] is True


# ── A2-3a: 레퍼런스 필터 · 스크린샷 ─────────────────────────────────────
def test_normalize_unusable_ref():
    spec = R.normalize_analysis({"usable": False, "usable_reason": "남성 코디 영상", "looks": [
        {"concept": "남친룩", "items": [{"kind": "top", "queries": ["남자 니트"]}]}]})
    assert spec["usable"] is False and spec["usable_reason"] == "남성 코디 영상" and spec["looks"] == []
    assert R.normalize_analysis({"looks": []})["usable"] is True                       # 판정 없으면 쓸 수 있음(이전 행 호환)


@needs_ffmpeg
def test_analyze_unusable_is_saved_not_failed(refs_env):
    refs_env.tables.t["ig_refs"].append({"video_id": "m1", "title": "명품 하울 토크", "thumb_key": "insta/refs/m1.jpg", "status": "new"})
    spec = R.analyze(refs_env.tables.t["ig_refs"][0], download=_download,
                     vision=lambda *a, **k: {"usable": False, "usable_reason": "명품 토크 영상"})
    row = refs_env.tables.t["ig_refs"][0]
    assert spec["usable"] is False and row["status"] == "analyzed" and row["analysis"]["usable_reason"] == "명품 토크 영상"


@needs_ffmpeg
def test_screenshot_ref(refs_env, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import insta as routes

    png = tmp_path / "s.png"
    _download("x", png)
    spec = {"looks": [{"concept": "가을 데이트룩", "items": [{"kind": "dress", "queries": ["여성 브라운 니트 원피스"]}]}]}
    out = R.add_screenshot(png.read_bytes(), "s.png", vision=lambda *a, **k: spec, download=_download)
    row = refs_env.tables.t["ig_refs"][0]
    assert row["source"] == "screenshot" and row["status"] == "analyzed" and row["video_id"].startswith("ss-")
    assert row["thumb_key"].startswith("insta/refs/screenshots/") and refs_env.s3.objs[row["thumb_key"]][0][:3] == b"\xff\xd8\xff"
    assert out["analysis"]["looks"][0]["concept"] == "가을 데이트룩"
    with pytest.raises(R.RefsError, match="png"):
        R.add_screenshot(b"x", "a.gif")
    app = FastAPI()
    app.include_router(routes.router, prefix="/insta")
    c = TestClient(app)
    assert c.post("/insta/refs/screenshot", files={"file": ("a.gif", b"x", "image/gif")}).status_code == 400
    listed = {r["video_id"]: r for r in c.get("/insta/refs").json()["refs"]}
    assert listed[row["video_id"]]["video_url"] is None and listed[row["video_id"]]["usable"] is True   # 스크린샷은 영상 링크 없음
