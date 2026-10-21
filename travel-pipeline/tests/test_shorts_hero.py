"""쇼츠 hero 형식 A — 박자·드롭 분석, 곡 소스, 레퍼런스, 금지 규칙, 파열 탐지·효과음 싱크, 두 버전 합성,
비용 상한·재생성, 클립 보관함, 앤섬(외부 API 실호출 없음 · ffmpeg 는 실제 실행)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import shorts_audio as sa  # noqa: E402
from services import shorts_hero as sh  # noqa: E402
from services import shorts_songs as ss  # noqa: E402

CH = "workout_music"
ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 필요")


def _ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def _song(path: Path, bpm: float, drop: float, dur: float, phase: float = 0.25):
    """박자가 분명한 합성 곡 — drop 이후 킥이 커지고 노이즈 패드가 깔린다."""
    beat = 60 / bpm
    expr = (f"if(lt(t,{drop}),0.12,0.6)*sin(2*PI*55*t)*exp(-30*mod(t-{phase}+10,{beat}))"
            f"+if(lt(t,{drop}),0.01,0.12)*(random(0)-0.5)")
    _ff("-f", "lavfi", "-i", f"aevalsrc='{expr}':s=22050:d={dur}", str(path))


# ── 박자 · 드롭 · 후렴 ───────────────────────────────────────────────────
@ffmpeg
@pytest.mark.parametrize("bpm,drop,dur", [(128, 60.0, 100), (80, 40.0, 75), (150, 30.0, 60)])
def test_analyze_bpm_drop_chorus(tmp_path, bpm, drop, dur):
    p = tmp_path / "s.wav"
    _song(p, bpm, drop, dur)
    a = sa.analyze(str(p))
    beat = 60 / bpm
    assert abs(a["bpm"] - bpm) <= 0.2, a
    assert abs(a["drop"] - drop) <= beat / 2 + 0.05, a                          # 드롭은 가장 가까운 박으로
    assert a["chorus_end"] - a["chorus_start"] == pytest.approx(25.0, abs=0.01)
    assert a["chorus_start"] == pytest.approx(a["drop"] - 8 * 60 / a["bpm"], abs=0.01)
    # 박 위상: 합성 킥 위치(phase 0.25 기준 격자)와 1프레임(33ms) 이내
    true_phase = (0.25 - 10) % beat
    err = min(abs(a["phase"] - true_phase), beat - abs(a["phase"] - true_phase))
    assert err <= 0.034, (a["phase"], true_phase)


# ── 곡 소스(업로드 영상 → 믹스 → 곡) ─────────────────────────────────────
def test_candidates_join_and_order(monkeypatch):
    monkeypatch.setattr(ss.r2_storage, "mastered_music_exists", lambda slug, aid: aid == "a2")
    monkeypatch.setattr(ss.r2_storage, "mastered_music_url", lambda slug, aid: f"https://m/{slug}/mastered/{aid}.mp3")
    monkeypatch.setattr(ss.r2_storage, "music_object_url", lambda k: f"https://m/{k}")
    uploads = [{"slug": "lib1", "mix_id": "m1", "youtube_url": "https://www.youtube.com/watch?v=V1",
                "youtube_video_id": "V1", "uploaded_at": "2026-10-20"},
               {"slug": "lib2", "mix_id": "m2", "youtube_url": "https://youtu.be/V2", "uploaded_at": "2026-10-19"}]
    mixes = {("lib1", "m1"): {"total_duration": 600, "tracks": [
        {"audio_id": "a1", "title": "A1", "language": "en", "start_sec": 0},
        {"audio_id": "a2", "title": "A2", "language": "inst", "start_sec": 200},
        {"audio_id": "a3", "title": "A3", "language": "en", "start_sec": 400}]},
        ("lib2", "m2"): {"total_duration": 300, "tracks": [{"audio_id": "a2", "start_sec": 0},
                                                           {"audio_id": "a4", "language": "inst", "start_sec": 100}]}}
    meta = {a: {"audio_id": a, "r2_key": f"music-masters/g/{a}.mp3"} for a in ("a1", "a2", "a3", "a4")}
    c = ss.candidates(CH, uploads=uploads, load_mix=lambda s, m: mixes[(s, m)],
                      get_tracks=lambda ids: [meta[i] for i in ids], exclude={"a3"})
    assert [x["audio_id"] for x in c] == ["a2", "a4", "a1"]                       # 연주곡 → 영어, 중복·제외
    a2 = c[0]
    assert a2["audio_url"] == "https://m/lib1/mastered/a2.mp3" and a2["start_in_video"] == 200
    assert a2["duration"] == 200 and a2["youtube_url"].endswith("V1")
    assert c[2]["audio_url"] == "https://m/music-masters/g/a1.mp3"               # 마스터본 없으면 원본
    assert ss.link_at("https://www.youtube.com/watch?v=V1", 214.7) == "https://www.youtube.com/watch?v=V1&t=214s"
    assert ss.link_at("https://youtu.be/V2", 5) == "https://youtu.be/V2?t=5s" and ss.mmss(134) == "2:14"


@ffmpeg
def test_analyze_song_chorus_position_in_video(tmp_path):
    src = tmp_path / "s.wav"
    _song(src, 120, 30.0, 50)
    cand = {"audio_id": "x", "audio_url": str(src), "youtube_url": "https://youtu.be/V", "start_in_video": 100.0}
    res = ss.analyze_song(cand, fetch=lambda u, p: shutil.copy(u, p))
    assert res["chorus_in_video"] == pytest.approx(100 + res["chorus_start"], abs=0.01)
    assert res["chorus_link"] == f"https://youtu.be/V?t={int(res['chorus_in_video'])}s"


# ── 금지 규칙 ────────────────────────────────────────────────────────────
def test_rules():
    c = sh.CONCEPTS["bat_break"]
    assert sh.check_rules(c["action"], c["note"]) == []                           # 기본 콘셉트·안전 문구는 통과
    bad = {
        "브랜드": "holding a Red Bull can", "실존 곡·가수": "music like We Will Rock You",
        "흡연·음주": "drinking beer after", "선정적 구도": "close-up of his crotch",
        "위험 행동": "try this at home!", "차량": "lifting a car with bare hands", "비하": "you are weak, ugly",
    }
    for why, text in bad.items():
        assert sh.check_rules(text), why
    assert sh.check_rules("기술과 예술") == []                                    # '술' 오탐 없음


# ── 레퍼런스(슬롯별 라벨) ────────────────────────────────────────────────
def test_select_refs_by_outfit():
    refs = {"face": ["F"], "shirtless": ["S"], "scale": ["K"], "casual": ["C"],
            "turnaround_shirtless:front": ["SF"], "turnaround_shirtless:side": ["SS1", "SS2"],
            "turnaround_shirtless:back": ["SB"], "turnaround:front": ["TF"], "turnaround:side": ["TS"],
            "expressions:expr": ["E1", "E2"]}
    assert sh.select_refs(refs, "shirtless") == ["F", "SF", "S", "SS1", "K", "SB"]
    assert sh.select_refs(refs, "sportswear") == ["F", "TF", "TS", "K", "E1"]     # 운동복 정면 ≠ 탈의 정면
    assert sh.select_refs(refs, "casual") == ["F", "C", "TF", "K", "E1"]
    assert len(sh.select_refs({**refs, "turnaround_shirtless:threequarter": ["ST"]}, "shirtless")) == 7


def test_slot_refs_keeps_slots_apart(monkeypatch):
    from services import shorts_cast as sc
    from services import shorts_cast_upload as up
    hero = {"role": "hero", "source": "upload", "slots": [
        {"key": "face", "kind": "single"}, {"key": "turnaround_shirtless", "kind": "strip"},
        {"key": "turnaround", "kind": "strip"}]}
    monkeypatch.setattr(sc, "get_entry", lambda ch, role: hero if role == "hero" else None)
    keys = ["face", "turnaround_shirtless", "turnaround"] + [f"turnaround_shirtless_p{i}" for i in range(4)] + \
           [f"turnaround_p{i}" for i in range(4)]
    monkeypatch.setattr(sc, "_list_objects", lambda ch: {f"cast/{ch}/hero/{k}.png": 1 for k in keys})
    monkeypatch.setattr(sc, "_aspect_url", lambda ch, role, k: f"u/{k}")
    monkeypatch.setattr(up, "read_meta", lambda ch: {"hero": {
        "turnaround_shirtless": {"crop": True, "labels": ["front", "side", "side", "back"]},
        "turnaround": {"crop": False, "labels": ["front", "side", "back", "side"]}}})
    r = sh.slot_refs(CH)
    assert r["turnaround_shirtless:front"] == ["u/turnaround_shirtless_p0"]
    assert r["turnaround_shirtless:side"] == ["u/turnaround_shirtless_p1", "u/turnaround_shirtless_p2"]
    assert r["turnaround:sheet"] == ["u/turnaround"] and "turnaround:front" not in r
    assert r["face"] == ["u/face"]


def test_hero_status(monkeypatch):
    from services import shorts_cast as sc
    monkeypatch.setattr(sc, "get_entry", lambda ch, role: None)
    assert sh.hero_status(CH) == {"ready": False, "reason": "hero 캐스트가 아직 없어요(#362 머지 필요)."}
    monkeypatch.setattr(sc, "get_entry", lambda ch, role: {"role": "hero"})
    monkeypatch.setattr(sc, "read_state", lambda ch: {})
    assert sh.hero_status(CH)["ready"] is False
    monkeypatch.setattr(sc, "read_state", lambda ch: {"hero": {"status": "approved", "version": sc.BIBLE_VERSION}})
    assert sh.hero_status(CH)["ready"] is True


# ── 파열 탐지 · 효과음 싱크 · 두 버전 (실제 ffmpeg) ──────────────────────
def _clip(path: Path, flash_at: float, dur: float = 10.0):
    _ff("-f", "lavfi", "-i", f"color=c=0x202020:s=720x1280:d={dur}:r=30", "-vf",
        f"drawbox=enable='between(t,{flash_at},{flash_at + 0.25})':x=100:y=300:w=500:h=600:color=white:t=fill",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path))


def _sfx(text, seconds, dest):
    """가짜 ElevenLabs — 소리 종류별로 다른 합성음."""
    if "room" in text:
        _ff("-f", "lavfi", "-i", f"anoisesrc=c=brown:a=0.02:d={seconds}", str(dest))
    elif "crack" in text:
        _ff("-f", "lavfi", "-i", "aevalsrc='0.9*(random(0)-0.5)*exp(-18*t)':d=2", str(dest))
    else:
        _ff("-f", "lavfi", "-i", "aevalsrc='0.3*sin(2*PI*140*t)*exp(-4*t)':d=1.2", str(dest))
    return {"path": str(dest), "seconds": seconds, "credits": int(round(seconds * 11))}


class _Kling:
    usd_per_sec = 0.24

    def __init__(self, path, model="kwaivgi/kling-video-o3-pro/reference-to-video"):
        self.path, self.model, self.calls = path, model, []

    async def generate(self, prompt, images, seconds):
        self.calls.append((prompt, images, seconds))
        return SimpleNamespace(url=str(self.path), seconds=seconds, cost_usd=round(seconds * 0.24, 3),
                               model=self.model, task_id="t")


def _ready(monkeypatch, refs=None):
    from services import shorts_cast as sc
    monkeypatch.setattr(sh, "hero_status", lambda ch=CH: {"ready": True, "reason": ""})
    monkeypatch.setattr(sh, "slot_refs", lambda ch=CH: refs or {"face": ["F"], "turnaround_shirtless:front": ["SF"],
                                                                 "shirtless": ["S"], "scale": ["K"]})
    monkeypatch.setattr(sc, "get_entry", lambda ch, role: {"role": "hero", "bible": "a 210 cm tall man"})


@ffmpeg
def test_produce_sync_two_versions_and_cost(monkeypatch, tmp_path):
    _ready(monkeypatch)
    clip = tmp_path / "kling.mp4"
    _clip(clip, 8.5)
    song = tmp_path / "song.wav"
    _song(song, 120, 20.0, 40)
    a = sa.analyze(str(song))
    k = _Kling(clip)
    run = sh.produce("bat_break", channel=CH, adapter=k, sfx_gen=_sfx,
                     reviewer=lambda c, d, w: {"pass": True, "reasons": []},
                     fetch=lambda u, p: shutil.copy(u, p),
                     song={**a, "audio_id": "s1", "audio_url": str(song), "youtube_url": "https://youtu.be/V",
                           "start_in_video": 300.0},
                     store=False)
    # 레퍼런스·프롬프트(리얼감·글자 없음)
    prompt, images, secs = k.calls[0]
    assert images == ["F", "SF", "S", "K"] and secs == 10
    assert "shot on a phone" in prompt and "NOT CGI" in prompt and "No text" in prompt and "210 cm" in prompt
    # 파열 탐지 ↔ 효과음 정렬
    assert abs(run["impact"]["t"] - 8.5) <= 1 / 30 + 0.001 and run["impact"]["guessed"] is False
    assert abs(run["sync"]["crack_err_ms"]) <= 34                                  # ±1프레임
    assert run["sync"]["breath_at"] == pytest.approx(run["impact"]["t"] + 0.45, abs=0.001)
    # 후렴 쾅: 두 버전 모두 파열음 피크를 -1dBFS 로 고정 → 파열 전엔 같고(음악 없음), 파열 뒤엔 후렴 버전이 더 크다
    t_imp = run["impact"]["t"]

    def windows(data: bytes, name: str) -> tuple[float, float]:
        f = tmp_path / name
        f.write_bytes(data)
        r = sa.rms_curve(sa.decode(str(f)))
        seg = lambda a, b: sum(r[int(a * sa.FPS):int(b * sa.FPS)]) / max(1, int((b - a) * sa.FPS))  # noqa: E731
        return seg(t_imp - 3.0, t_imp - 0.3), seg(t_imp + 0.6, t_imp + 1.4)
    s_before, s_after = windows(run["_files"]["sfx"], "sfx_r.mp4")
    m_before, m_after = windows(run["_files"]["slam"], "slam.mp4")
    assert m_before == pytest.approx(s_before, rel=0.35)                          # 파열 전: 음악 없음
    assert m_after > 0 and s_after > 0         # 파열 뒤 음악 정렬·크기는 test_slam_music_beat_aligns_to_impact
    assert s_before < 0.05                                                        # 앞부분은 조용(무음 긴장 유지)
    sfx_only = tmp_path / "sfx.mp4"
    sfx_only.write_bytes(run["_files"]["sfx"])
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height",
                                       "-of", "json", str(sfx_only)], capture_output=True, text=True).stdout)
    v = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1080, 1920) and any(s["codec_type"] == "audio" for s in probe["streams"])
    # 비용·관련 동영상·설명란
    assert run["cost"]["kling_usd"] == pytest.approx(2.4) and run["cost"]["attempts"] == 1
    assert run["cost"]["sfx_credits"] == 110 + 22 + 13
    drop_pos = 300 + a["drop"]
    assert run["related"]["link"] == f"https://youtu.be/V?t={int(drop_pos)}s"
    assert run["description"].splitlines()[0].startswith("▶ 전체 운동 플리: https://youtu.be/V")
    assert "따라 하지 마세요" in run["description"] and sh.check_rules(run["description"]) == []


@ffmpeg
def test_review_retry_and_cost_cap(monkeypatch, tmp_path):
    _ready(monkeypatch)
    clip = tmp_path / "kling.mp4"
    _clip(clip, 8.0)
    k = _Kling(clip)
    verdicts = iter([{"pass": False, "reasons": ["손가락 6개"]}, {"pass": False, "reasons": ["CG 피부"]},
                     {"pass": True, "reasons": []}])
    monkeypatch.setenv("SHORTS_MAX_USD_PER_EPISODE", "6")
    run = sh.produce("bat_break", adapter=k, sfx_gen=_sfx, reviewer=lambda c, d, w: next(verdicts),
                     fetch=lambda u, p: shutil.copy(u, p), song=False, store=False)
    # $2.4 × 2회 = $4.8, 3회째는 $7.2 > $6 이라 멈춤 → 마지막 검수(불합격) 그대로 기록
    assert run["cost"]["attempts"] == 2 and run["cost"]["kling_usd"] == pytest.approx(4.8)
    assert run["cost"]["stopped_by_cap"] is True and run["review"]["pass"] is False
    assert "Avoid: 손가락 6개" in k.calls[1][0]                                   # 불합격 사유를 다음 프롬프트에
    assert "slam" not in run.get("previews", {}) and run["_files"]["slam"] is None   # 곡 없으면 음악 없음 버전만
    monkeypatch.setenv("SHORTS_MAX_USD_PER_EPISODE", "2")
    with pytest.raises(RuntimeError, match="비용 상한"):
        sh.produce("bat_break", adapter=_Kling(clip), sfx_gen=_sfx, reviewer=lambda *a: {"pass": True},
                   fetch=lambda u, p: shutil.copy(u, p), song=False, store=False)


def test_not_ready_blocks(monkeypatch):
    monkeypatch.setattr(sh, "hero_status", lambda ch=CH: {"ready": False, "reason": "hero 캐릭터 시트를 확정해 주세요"})
    with pytest.raises(sh.HeroNotReady, match="확정"):
        sh.produce("bat_break", adapter=_Kling("x"), store=False)


@ffmpeg
def test_impact_guess_when_no_flash(tmp_path):
    clip = tmp_path / "flat.mp4"
    _ff("-f", "lavfi", "-i", "color=c=gray:s=360x640:d=6:r=30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip))
    imp = sa.impact_time(str(clip), 6.0)
    assert imp["guessed"] is True and imp["t"] == pytest.approx(5.1)


# ── 클립 보관함 · 실행 기록 · 앤섬 ───────────────────────────────────────
def test_store_clip_and_runs(monkeypatch, tmp_path):
    from test_workout_image_reuse import _FakeS3
    s3 = _FakeS3()
    monkeypatch.setattr(sh.r2_storage, "is_available", lambda: True)
    monkeypatch.setattr(sh.r2_storage, "_get_client", lambda: s3)
    monkeypatch.setattr(sh.r2_storage, "_music_bucket", lambda: "music")
    monkeypatch.setattr(sh, "_put_video", lambda p, key: f"https://pub/{key}")
    f = tmp_path / "c.mp4"
    f.write_bytes(b"x")
    item = sh.store_clip(CH, f, {"format": "A", "outfit": "shirtless", "review": {"pass": True}})
    idx = json.loads(s3.objs["shorts/workout_music/clips/index.json"][0])
    assert idx[0]["id"] == item["id"] and idx[0]["url"].startswith("https://pub/shorts/workout_music/clips/")
    assert idx[0]["outfit"] == "shirtless" and idx[0]["used_in"] == []
    sh.save_run(CH, {"id": "r1", "status": "preview_ready"})
    sh.save_run(CH, {"id": "r2", "status": "preview_ready"})
    sh.save_run(CH, {"id": "r1", "status": "failed"})
    assert [r["id"] for r in sh.read_runs(CH)] == ["r1", "r2"] and sh.read_runs(CH)[0]["status"] == "failed"


def test_anthem_theme_and_generate():
    t = sh.anthem_theme(CH)
    assert t["instrumental"] is True and t["channel"] == CH and t["language"] == "inst"
    assert "80 BPM" in t["style"] and "stomp" in t["style"] and "guitar" in t["style"]
    assert sh.check_rules(t["style"], t.get("title", "")) == []                   # 실존 곡명 없음
    got = {}
    res = sh.make_anthem(CH, generate=lambda theme, channel: got.update(theme=theme, ch=channel) or
                         {"tracks": [{"audio_id": "a"}, {"audio_id": "b"}]})
    assert got["ch"] == CH and [t["audio_id"] for t in res["tracks"]] == ["a", "b"]  # 1회 = 2클립
    assert sh.anthem_state()["status"] == "done"


@ffmpeg
@pytest.mark.parametrize("impact_t", [6.2, 8.5])
def test_slam_music_beat_aligns_to_impact(tmp_path, impact_t):
    """후렴 쾅: 곡 드롭(박에 맞춘 시각)의 첫 킥이 영상 파열 순간에 오는지 — 정렬 오차 ±1프레임."""
    song = tmp_path / "song.wav"
    _song(song, 128, 30.0, 50)
    a = sa.analyze(str(song))
    sfx = tmp_path / "sfx.wav"
    _ff("-f", "lavfi", "-i", "anoisesrc=c=brown:a=0.002:d=10", "-ar", "44100", "-ac", "2", str(sfx))
    out = tmp_path / "slam.wav"
    sh.mix_slam(sfx, song, a["drop"], impact_t, 10.0, out, tmp_path)
    t = sh.audio_peak_time(out, after=impact_t - 1.0)
    err_ms = (t - impact_t) * 1000
    assert abs(err_ms) <= 34, err_ms
    r = sa.rms_curve(sa.decode(str(out)))
    seg = lambda x, y: sum(r[int(x * sa.FPS):int(y * sa.FPS)]) / max(1, int((y - x) * sa.FPS))  # noqa: E731
    assert seg(impact_t + 0.1, impact_t + 1.0) > 5 * seg(impact_t - 2.0, impact_t - 0.2)    # 파열 전엔 음악 없음


@ffmpeg
def test_sfx_mix_keeps_quiet_intro(tmp_path):
    """loudnorm 대신 피크 정규화 — 앞부분 룸톤은 조용히, 파열음 피크만 -1dBFS 근처."""
    files = {}
    for name, text, sec in (("room", "room", 10), ("impact", "crack", 2), ("breath", "grunt", 1.2)):
        files[name] = tmp_path / f"{name}.mp3"
        _sfx(text, sec, files[name])
    out = tmp_path / "sfx.wav"
    sh.mix_sfx(files["room"], files["impact"], files["breath"], 10.0, 8.5, 8.95, out, tmp_path)
    r = sa.rms_curve(sa.decode(str(out)))
    intro = sum(r[: int(8 * sa.FPS)]) / int(8 * sa.FPS)
    peak = max(r[int(8.4 * sa.FPS): int(8.8 * sa.FPS)])
    assert peak > 20 * intro and intro < 0.02
    assert abs(sh.audio_peak_time(out, after=7.5, before=8.8) - 8.5) <= 0.034


def test_routes_gate_and_busy(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes import shorts_hero as rh
    from services import shorts_produce
    monkeypatch.setattr(ss, "read_analysis", lambda ch=CH: {"a": {"audio_id": "a", "analyzed_at": "1"}})
    monkeypatch.setattr(sh, "read_runs", lambda ch=CH: [])
    app = FastAPI()
    app.include_router(rh.router, prefix="/shorts/hero")
    c = TestClient(app)
    monkeypatch.setattr(sh, "hero_status", lambda ch=CH: {"ready": False, "reason": "hero 캐릭터 시트를 확정해 주세요"})
    home = c.get("/shorts/hero").json()
    assert home["hero"]["ready"] is False and home["concepts"][0]["id"] == "bat_break" and home["cap_usd"] == 6.0
    r = c.post("/shorts/hero/test", json={})
    assert r.status_code == 400 and "확정" in r.json()["detail"]                   # hero 확정 전엔 막힘
    assert c.post("/shorts/hero/test", json={"concept": "nope"}).status_code == 400
    monkeypatch.setattr(sh, "hero_status", lambda ch=CH: {"ready": True, "reason": ""})
    started = []
    monkeypatch.setattr(sh, "run_background", lambda concept, channel: started.append(concept))
    monkeypatch.setattr(shorts_produce, "music_busy", lambda: False)
    assert c.post("/shorts/hero/test", json={}).json()["status"] == "running" and started == ["bat_break"]
    monkeypatch.setattr(shorts_produce, "music_busy", lambda: True)
    assert c.post("/shorts/hero/test", json={}).status_code == 409
    monkeypatch.setattr(sh, "anthem_state", lambda: {"status": "running"})
    assert c.post("/shorts/hero/anthem", json={}).status_code == 409
