"""쇼츠 시즌 1 — 시리즈·대본 규칙·레퍼런스 선택·Kling O3 어댑터·아기 대체·합성(외부 API 실호출 없음)."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.video import wavespeed_ref_video_adapter as rv  # noqa: E402
from services import shorts_produce as sp  # noqa: E402
from services import shorts_refs, shorts_script, shorts_series  # noqa: E402
from test_workout_image_reuse import _FakeS3  # noqa: E402

CH = "workout_music"


# ── 시리즈 ───────────────────────────────────────────────────────────────
def test_series_plan_and_stages():
    s = shorts_series.initial_series(CH)
    eps = s["episodes"]
    assert [e["day"] for e in eps] == list(range(1, 16)) and eps[-1]["finale"] is True
    assert [e["dday"] for e in eps][:2] == ["D-14", "D-13"] and eps[13]["dday"] == "D-1" and eps[14]["dday"] == "D-day"
    assert [shorts_series.mom_stage(d) for d in (1, 6, 7, 11, 12, 15)] == [
        "mom", "mom", "mom_mid", "mom_mid", "mom_after", "mom_after"]
    # 테스트 3편(대표 추천): Day1 엄마 단독 / Day4 엄마+아빠 / Day6 엄마+아기
    by = {e["day"]: e for e in eps}
    assert by[1]["characters"] == ["mom"] and set(by[4]["characters"]) == {"dad", "mom"}
    assert set(by[6]["characters"]) == {"mom", "baby"}
    fmts = [e["format"] for e in eps]
    assert fmts.count("A") == 4 and fmts.count("B") == 6 and fmts.count("C") == 5


def test_series_r2_roundtrip(monkeypatch):
    from adapters import r2_storage
    s3 = _FakeS3()
    monkeypatch.setattr(r2_storage, "is_available", lambda: True)
    monkeypatch.setattr(r2_storage, "_get_client", lambda: s3)
    monkeypatch.setattr(r2_storage, "_music_bucket", lambda: "music")
    assert shorts_series.load(CH)["episodes"][0]["status"] == "planned"        # 없으면 초기 계획
    shorts_series.update_episode(CH, 1, status="uploaded_private", summary="원피스 결심")
    shorts_series.update_episode(CH, 2, summary="스쿼트 첫날")
    s = shorts_series.load(CH)
    assert shorts_series.episode(s, 1)["status"] == "uploaded_private"
    assert shorts_series.previous_summaries(s, 4) == ["Day 1: 원피스 결심", "Day 2: 스쿼트 첫날"]
    assert "shorts/workout_music/series.json" in s3.objs


# ── 대본 규칙 ────────────────────────────────────────────────────────────
GOOD = {
    "hook": "돌잔치까지 2주…",
    "captions": ["원피스 지퍼가 안 올라간다", "오늘부터 엄마 체력 챌린지 시작!"],
    "voice_line": "2주면 할 수 있어",
    "scenes": [
        {"seconds": 8, "place": "안방", "characters": ["mom"],
         "action_en": "The mom holds a dress up in front of a mirror, takes a deep breath and smiles with determination. Full-body shot."},
        {"seconds": 10, "place": "거실", "characters": ["mom"],
         "action_en": "She ties her ponytail and starts stretching on a yoga mat, above-the-knee medium shot."},
    ],
    "summary": "돌잔치 원피스를 보고 2주 챌린지를 결심했다",
}


def test_check_rules_clean_and_violations():
    assert shorts_script.check_rules(GOOD) == [] and shorts_script.check_shape(GOOD, ["mom"]) == []
    bad_cases = {
        "체중 숫자": {"captions": ["목표 -5kg!"]},
        "체중 언급": {"hook": "몸무게 재기"},
        "다이어트": {"captions": ["오늘부터 다이어트"]},
        "체형 비하": {"captions": ["뱃살 어떡해"]},
        "선정적": {"scenes": [{"action_en": "sexy pose", "characters": ["mom"], "seconds": 5}]},
        "클로즈업": {"scenes": [{"action_en": "close-up of her hips while squatting", "characters": ["mom"], "seconds": 5}]},
        "로고": {"scenes": [{"action_en": "wearing Nike shoes", "characters": ["mom"], "seconds": 5}]},
    }
    for why, patch in bad_cases.items():
        s = {**GOOD, **patch}
        assert shorts_script.check_rules(s), why
    baby = {**GOOD, "scenes": [{"seconds": 8, "characters": ["mom", "baby"], "caption": "아기 뱃살도 쏙",
                                "action_en": "The baby copies the stretch on the mat."}]}
    assert any("아기" in r or "체형" in r for r in shorts_script.check_rules(baby))
    # '한 살' 같은 말은 아기 규칙에 걸리지 않음
    ok_baby = {**GOOD, "scenes": [{"seconds": 15, "characters": ["mom", "baby"], "caption": "한 살 아기도 따라 하기",
                                   "action_en": "The baby claps and imitates mom's stretch on the mat, full-body shot."}]}
    assert shorts_script.check_rules(ok_baby) == []


def test_check_shape():
    assert "총 길이" in " ".join(shorts_script.check_shape({**GOOD, "scenes": GOOD["scenes"][:1]}, ["mom"]))
    assert any("등장 인물" in e for e in shorts_script.check_shape(GOOD, ["dad"]))


def _series_ep(day):
    s = shorts_series.initial_series(CH)
    return s, shorts_series.episode(s, day)


def test_generate_retries_until_clean_and_exclude_baby():
    calls = []
    outs = [json.dumps({**GOOD, "captions": ["5kg 빼자"]}), json.dumps(GOOD)]

    def fake(system, user):
        calls.append(user)
        return outs.pop(0)
    s, ep = _series_ep(1)
    script = shorts_script.generate(s, ep, call=fake)
    assert script["attempts"] == 2 and "체중 숫자" in calls[1]                 # 위반 사유를 붙여 재시도
    # 아기 제외 대본: 등장 인물에서 baby 빠지고 프롬프트에 대체 지시
    s, ep = _series_ep(6)
    got = {}

    def fake2(system, user):
        got["u"] = user
        return json.dumps({**GOOD})
    script = shorts_script.generate(s, ep, exclude=("baby",), call=fake2)
    assert script["characters"] == ["mom"] and "아기 없이" in got["u"]
    with pytest.raises(shorts_script.ScriptRejected):
        shorts_script.generate(s, ep, call=lambda a, b: json.dumps({**GOOD, "hook": "뚱뚱한 엄마"}))


# ── 레퍼런스 선택 ────────────────────────────────────────────────────────
def _fake_refs(role, approved=("dad", "mom", "mom_after", "baby", "family"), with_finale=False):
    if role not in approved:
        return {}
    b = f"https://r2/{role}/"
    if role == "family":
        out = {"group": [b + "group.png"]}
        if with_finale:
            out["finale"] = [b + "finale.png"]
        return out
    if role == "mom_after":
        return {"face": [b + "face.png"], "fullbody": [b + "fullbody.png"]}
    out = {"face": [b + "face.png"], "front": [b + "turnaround_p0.png"], "side": [b + "turnaround_p1.png"],
           "expr": [b + "expressions_p0.png"]}
    if role == "mom":
        out.update(action_front=[b + "action_front.png"], action_side=[b + "action_side.png"])
    else:
        out["action"] = [b + "action.png"]
    return out


@pytest.fixture
def refs(monkeypatch):
    state = {"approved": ("dad", "mom", "mom_after", "baby", "family"), "finale": False}
    monkeypatch.setattr(shorts_refs.up, "labeled_refs",
                        lambda ch, role: _fake_refs(role, state["approved"], state["finale"]))
    return state


def test_select_single_two_three(refs):
    r = shorts_refs.select(CH, ["mom"], fmt="B")
    assert r["images"][:2] == ["https://r2/mom/face.png", "https://r2/mom/turnaround_p0.png"]
    assert "https://r2/mom/action_front.png" in r["images"] and len(r["images"]) <= 7
    assert "freckles" in r["bible"]
    r = shorts_refs.select(CH, ["dad", "mom"], fmt="B")
    assert r["images"][:5] == ["https://r2/dad/face.png", "https://r2/dad/turnaround_p0.png",
                               "https://r2/mom/face.png", "https://r2/mom/turnaround_p0.png",
                               "https://r2/family/group.png"]
    r = shorts_refs.select(CH, ["dad", "mom", "baby"], fmt="C")
    assert len(r["images"]) == 7 and "https://r2/family/group.png" in r["images"]
    assert {u for u in r["images"] if u.endswith("face.png")} == {
        "https://r2/dad/face.png", "https://r2/mom/face.png", "https://r2/baby/face.png"}
    r = shorts_refs.select(CH, ["mom"], fmt="A")
    assert "https://r2/mom/expressions_p0.png" in r["images"]                   # 셀카 → 표정


def test_select_mom_stages_finale_and_unapproved(refs):
    r = shorts_refs.select(CH, ["mom"], mom_stage="mom_mid")
    assert r["images"][:2] == ["https://r2/mom/face.png", "https://r2/mom_after/fullbody.png"]
    assert "midway" in r["bible"]
    r = shorts_refs.select(CH, ["mom"], mom_stage="mom_after")
    assert r["images"][:2] == ["https://r2/mom_after/face.png", "https://r2/mom_after/fullbody.png"]
    refs["finale"] = True
    r = shorts_refs.select(CH, ["dad", "mom", "baby"], mom_stage="mom_after", fmt="C", finale=True)
    assert "https://r2/family/finale.png" in r["images"] and "https://r2/family/group.png" not in r["images"]
    refs["approved"] = ("dad", "mom", "mom_after", "family")
    with pytest.raises(shorts_refs.CastNotReady, match="baby"):
        shorts_refs.select(CH, ["mom", "baby"])


# ── Kling O3 Reference 어댑터 ────────────────────────────────────────────
def _transport(responses):
    seen = []

    def handler(req: httpx.Request):
        seen.append((req.method, str(req.url), json.loads(req.content) if req.content else None))
        return responses.pop(0)
    return httpx.MockTransport(handler), seen


def test_adapter_payload_cost_and_block(monkeypatch):
    monkeypatch.setenv("WAVESPEED_API_KEY", "K")
    monkeypatch.setattr(rv, "_POLL_SEC", 0)
    ok = [httpx.Response(200, json={"data": {"id": "t1"}}),
          httpx.Response(200, json={"data": {"status": "processing"}}),
          httpx.Response(200, json={"data": {"status": "completed", "outputs": ["https://cdn/v.mp4"]}})]
    tr, seen = _transport(ok)
    a = rv.kling()
    res = asyncio.run(a.generate("p", [f"u{i}" for i in range(9)], 10, client=httpx.AsyncClient(transport=tr)))
    method, url, body = seen[0]
    assert url.endswith("/kwaivgi/kling-video-o3-pro/reference-to-video")
    assert body == {"prompt": "p", "images": [f"u{i}" for i in range(7)], "duration": 10,
                    "aspect_ratio": "9:16", "sound": False}
    assert res.url == "https://cdn/v.mp4" and res.cost_usd == pytest.approx(2.4)   # $1.20/5초
    tr, _ = _transport([httpx.Response(400, text='{"message":"Reference content cannot include real human faces"}')])
    with pytest.raises(rv.RefBlocked):
        asyncio.run(a.generate("p", ["u"], 5, client=httpx.AsyncClient(transport=tr)))
    tr, _ = _transport([httpx.Response(200, json={"data": {"id": "t2"}}),
                        httpx.Response(200, json={"data": {"status": "failed", "error": "input image contains a minor"}})])
    with pytest.raises(rv.RefBlocked):
        asyncio.run(a.generate("p", ["u"], 5, client=httpx.AsyncClient(transport=tr)))
    tr, _ = _transport([httpx.Response(404, text="model not found")])
    with pytest.raises(RuntimeError) as ei:
        asyncio.run(a.generate("p", ["u"], 5, client=httpx.AsyncClient(transport=tr)))
    assert not isinstance(ei.value, rv.RefBlocked)


# ── 아기 차단 → 엄마·아빠 대본 대체 / Seedance 비교 ──────────────────────
class _FakeVideo:
    model_id = "fake"

    def __init__(self, block_baby=False, block_all=False):
        self.block_baby, self.block_all, self.calls = block_baby, block_all, []

    async def generate(self, prompt, images, seconds):
        self.calls.append(images)
        if self.block_all or (self.block_baby and any("/baby/" in u for u in images)):
            raise rv.RefBlocked("input contains a minor")
        return rv.RefVideoResult("https://cdn/x.mp4", seconds, round(seconds * 0.24, 3), "fake", "t")


def _fake_script(series, ep, exclude=()):
    chars = [c for c in ep["characters"] if c not in exclude]
    return {**GOOD, "characters": chars,
            "scenes": [{**GOOD["scenes"][0], "characters": chars}, {**GOOD["scenes"][1], "characters": chars}]}


def test_baby_blocked_falls_back_to_parents(refs):
    s, ep = _series_ep(6)
    v = _FakeVideo(block_baby=True)
    script, clips, notes = sp.make_clips(s, ep, adapter=v, gen_script=_fake_script)
    assert notes["baby_dropped"] is True and script["characters"] == ["mom"]
    assert len(clips) == 2 and all("/baby/" not in u for c in clips for u in c["refs"])
    assert sum(c["cost_usd"] for c in clips) == pytest.approx(18 * 0.24)
    s, ep = _series_ep(4)                                                        # 아기 없는 장면 거부는 그대로 실패
    with pytest.raises(rv.RefBlocked):
        sp.make_clips(s, ep, adapter=_FakeVideo(block_all=True), gen_script=_fake_script)


def test_seedance_probe_records_result(refs):
    s, ep = _series_ep(1)
    script = _fake_script(s, ep)
    out = sp.seedance_probe(ep, script, adapter=_FakeVideo(block_all=True))
    assert out["accepted"] is False and out["blocked"] is True and "minor" in out["error"]
    out = sp.seedance_probe(ep, script, adapter=_FakeVideo())
    assert out["accepted"] is True


# ── 합성(실제 ffmpeg) ────────────────────────────────────────────────────
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 필요")
def test_assemble_vertical_with_subs_and_music(tmp_path):
    for i, (w, h) in enumerate([(720, 1280), (1280, 720)]):                    # 비율이 달라도 1080×1920 로
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=blue:s={w}x{h}:d=3:r=24",
                        str(tmp_path / f"c{i}.mp4")], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=2",
                    str(tmp_path / "music.mp3")], check=True)
    out = tmp_path / "short.mp4"
    dur = sp.assemble([tmp_path / "c0.mp4", tmp_path / "c1.mp4"], GOOD, tmp_path / "music.mp3", out, tmp_path)
    assert dur == pytest.approx(6, abs=0.3)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height",
                            "-of", "json", str(out)], capture_output=True, text=True).stdout
    streams = json.loads(probe)["streams"]
    v = next(s for s in streams if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1080, 1920) and any(s["codec_type"] == "audio" for s in streams)
    ass = (tmp_path / "subs.ass").read_text()
    assert "돌잔치까지 2주" in ass and "PlayResY: 1920" in ass


def test_subtitles_and_metadata():
    items = sp.subtitle_items(GOOD, 18.0)
    assert items[0]["subtitle"] == GOOD["hook"] and items[0]["end"] == 2.0
    assert len(items) == 3 and items[-1]["end"] <= 18.0
    s, ep = _series_ep(1)
    title, desc, tags = sp.build_metadata(ep, GOOD)
    assert len(title) <= 100 and "#Shorts" in title and "D-14" in title
    assert "AI로 생성한 가상 인물" in desc and "#Shorts" in desc and "shorts" in tags


# ── 라우트 / 확정 확인 ───────────────────────────────────────────────────
def test_test_run_requires_all_approved(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes import shorts
    from services import shorts_cast
    state = {"dad": {"status": "approved", "version": shorts_cast.BIBLE_VERSION}}
    monkeypatch.setattr(shorts_cast, "read_state", lambda ch: state)
    assert sp.unapproved_roles() == ["mom", "mom_after", "baby", "family"]
    app = FastAPI()
    app.include_router(shorts.router, prefix="/shorts")
    c = TestClient(app)
    r = c.post("/shorts/test-run", json={})
    assert r.status_code == 400 and "mom" in r.json()["detail"]
    for role in ("mom", "mom_after", "baby", "family"):
        state[role] = {"status": "approved", "version": shorts_cast.BIBLE_VERSION}
    started = []
    monkeypatch.setattr(sp, "run_test", lambda days, **kw: started.append((days, kw)))
    assert c.post("/shorts/test-run", json={"days": [1, 2, 3, 4]}).status_code == 400
    r = c.post("/shorts/test-run", json={})
    assert r.status_code == 200 and started == [([1, 4, 6], {"channel": CH, "compare_seedance": True, "upload": False})]
    started.clear()
    r = c.post("/shorts/test-run", json={"days": [1]})
    assert r.status_code == 200 and r.json()["upload"] is False and started[0][0] == [1]
    monkeypatch.setattr(sp, "music_busy", lambda: True)
    assert c.post("/shorts/test-run", json={}).status_code == 409


def test_produce_episode_saves_preview_without_upload(monkeypatch, tmp_path):
    """테스트 기본: 유튜브 업로드 없이 R2 미리보기만 저장하고 series 에 preview_url 기록."""
    from services import sayeon_assemble
    saved, uploaded, updates = [], [], []
    monkeypatch.setattr(sp.shorts_series, "load", lambda ch: {"episodes": []})
    ep1 = _series_ep(1)[1]
    monkeypatch.setattr(sp.shorts_series, "episode", lambda s, d: ep1)
    monkeypatch.setattr(sp.shorts_series, "update_episode",
                        lambda ch, d, **f: updates.append(f) or dict(f))
    monkeypatch.setattr(sp, "make_clips", lambda series, ep, channel: (
        {"hook": "h", "captions": ["c"], "summary": "s", "scenes": []},
        [{"scene": 0, "url": "u", "seconds": 5, "cost_usd": 1.2}], {}))
    monkeypatch.setattr(sp, "pick_music", lambda ch: None)
    monkeypatch.setattr(sayeon_assemble, "_fetch", lambda url, p: p.write_bytes(b"x"))
    monkeypatch.setattr(sp, "assemble", lambda paths, script, music, out, cwd: out.write_bytes(b"mp4") or 15.0)
    monkeypatch.setattr(sp, "save_preview", lambda mp4, ch, day: saved.append(day) or "https://r2/p.mp4")
    monkeypatch.setattr(sp, "upload_private", lambda *a, **k: uploaded.append(1) or {})
    res = sp.produce_episode(1)
    assert saved == [1] and uploaded == []
    assert res["status"] == "rendered" and res["preview_url"] == "https://r2/p.mp4" and res["video_id"] is None
    assert sp.preview_key(CH, 3).startswith(f"shorts/{CH}/previews/day03-")
