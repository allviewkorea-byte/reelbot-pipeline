"""운동 채널 AI 배경(PR-1) 검증 — 외부 호출(OpenAI·Claude·R2·Supabase)은 전부 가짜로 막는다.

실행: travel-pipeline 에서 `python -m pytest tests/test_music_auto_image.py -q`
(ffmpeg 필요 — 검수용 축소·PNG 변환이 ffmpeg 를 쓴다.)
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import music_auto_image as mai  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg 필요")


def _png_bytes(tmp_path: Path, color: str = "red") -> bytes:
    p = tmp_path / f"src_{color}.png"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=64x36", "-frames:v", "1", str(p)],
        check=True, capture_output=True,
    )
    return p.read_bytes()


# ── 프롬프트 ──────────────────────────────────────────────────────────
def test_build_prompt_strips_tag_and_uses_bright_tone(monkeypatch):
    from services import music_image_prompts as mip
    monkeypatch.setattr(mip, "_generate_workout_prompt", lambda ex: (_ for _ in ()).throw(RuntimeError("no llm")))
    p = mai.build_prompt("running")
    assert "[WORKOUT]" not in p
    for phrase in (
        "한 폭의 그림 같은 분위기",
        "밝은 햇살과 자연광",
        "빨강·노랑·코발트 블루",
        "어둡고 칙칙한 톤·회색조 금지",
        "화면 중앙은 하얗게 날리지 말 것",
        "화면 중앙에 창문·출입구·역광 광원을 두지 말 것",
        "간판·포스터·벽 글자 등 읽히는 문구 금지",
        "글로벌 스포츠웨어 브랜드 캠페인 화보",
        "크롭탑·스포츠브라 단독·짧은 반바지 금지",
        "얼굴 정면 클로즈업 금지",
        "완벽하게 정돈하지 말 것",
        "보는 순간 몸을 움직이고 싶어지는 느낌",
    ):
        assert phrase in p, phrase
    for dark in ("어둡고 무게감", "깊은 그림자", "저녁 빛"):
        assert dark not in p, dark


def test_workout_pool_tone_and_single_definition():
    from services import music_image_prompts as mip
    assert {k: len(v) for k, v in mip.WORKOUT_IMAGE_PROMPTS.items()} == {"strength": 15, "cardio": 15, "warmup": 15}
    blob = " ".join(sum(mip.WORKOUT_IMAGE_PROMPTS.values(), [])) + " ".join(mip.WORKOUT_SUFFIX.values())
    for dark in ("어둡", "무게감", "깊은 그림자", "야간", "형광등"):
        assert dark not in blob, dark
    # 톤은 한 곳(WORKOUT_TONE) — 세 소비처가 같은 문자열을 쓴다.
    assert mip.WORKOUT_TONE in mip._WORKOUT_PREFIX
    assert mip.WORKOUT_TONE in mip._WORKOUT_GEN_SYSTEM
    assert mip.WORKOUT_TONE in mai.api_prefix()
    assert "어둡고 무게감" not in mip._WORKOUT_GEN_SYSTEM


def test_review_criteria_updated():
    r = mai._REVIEW_SYSTEM
    assert "전체가 어둡거나 칙칙하다" in r and "화면 중앙이 하얗게 날아가" in r
    assert "운동과 무관한 카페·거리" in r and "밝고 화사한" not in r
    for phrase in ("크롭탑", "스포츠브라 단독", "짧은 반바지", "얼굴 정면 클로즈업", "간판·포스터",
                   "AI 티", "원판 무게 숫자", "읽혀도 정상", "글로벌 스포츠웨어 브랜드 캠페인 화보"):
        assert phrase in r, phrase


def test_env_overrides(monkeypatch):
    monkeypatch.delenv("MUSIC_IMAGE_MODEL", raising=False)
    assert (mai.image_model(), mai.image_size(), mai.image_quality()) == ("gpt-image-2.5-flare", "2048x1152", "high")
    monkeypatch.setenv("MUSIC_IMAGE_MODEL", "gpt-image-2.5-sunburst")
    monkeypatch.setenv("MUSIC_IMAGE_QUALITY", "xhigh")
    assert mai.image_model() == "gpt-image-2.5-sunburst" and mai.image_quality() == "xhigh"


def test_wants_auto_image():
    assert mai.wants_auto_image("workout_music", None) is True
    assert mai.wants_auto_image("workout_music", False) is False
    for ch in (None, "", "unknown"):
        assert mai.wants_auto_image(ch, True) is False
    # where: 자동 회차가 채널을 'rooftop_music' 으로 명시하고 True 를 줄 때만(수동 화면은 미전송 → False)
    assert mai.wants_auto_image("rooftop_music", True) is True
    assert mai.wants_auto_image("rooftop_music", None) is False
    assert mai.wants_auto_image(None, None) is False


# ── 이미지 생성(응답 형식 방어) ───────────────────────────────────────
class _FakeImages:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def generate(self, **kw):
        self.calls.append(kw)
        return self.payload


def _install_fake_openai(monkeypatch, payload):
    images = _FakeImages(payload)
    mod = types.ModuleType("openai")
    images.client_kwargs = {}
    mod.OpenAI = lambda **kw: images.client_kwargs.update(kw) or types.SimpleNamespace(images=images)
    monkeypatch.setitem(sys.modules, "openai", mod)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    return images


def test_generate_image_b64(monkeypatch, tmp_path):
    raw = _png_bytes(tmp_path)
    usage = types.SimpleNamespace(model_dump=lambda: {"output_tokens": 2000, "input_tokens": 300})
    resp = types.SimpleNamespace(data=[types.SimpleNamespace(b64_json=base64.b64encode(raw).decode(), url=None)], usage=usage)
    images = _install_fake_openai(monkeypatch, resp)
    info = mai.generate_image("p", str(tmp_path / "out.png"))
    assert (tmp_path / "out.png").read_bytes() == raw
    assert images.calls[0] == {"model": "gpt-image-2.5-flare", "prompt": "p", "size": "2048x1152", "quality": "high", "n": 1}
    assert "response_format" not in images.calls[0]
    # 단계 상한: 이미지 1회 180초·재시도 0(SDK 기본 600초×2회 대신)
    assert images.client_kwargs["timeout"] == 180.0 and images.client_kwargs["max_retries"] == 0
    assert info["response_format"] == "b64_json" and info["est_output_usd"] == 0.06


def test_generate_image_url_and_jpeg_converted(monkeypatch, tmp_path):
    jpg = tmp_path / "x.jpg"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x36", "-frames:v", "1", str(jpg)],
                   check=True, capture_output=True)
    resp = types.SimpleNamespace(data=[types.SimpleNamespace(b64_json=None, url="https://x/y")], usage=None)
    _install_fake_openai(monkeypatch, resp)
    import httpx
    monkeypatch.setattr(httpx, "get", lambda url, **kw: types.SimpleNamespace(content=jpg.read_bytes(), raise_for_status=lambda: None))
    info = mai.generate_image("p", str(tmp_path / "out.png"))
    assert info["response_format"] == "url" and info["image_kind"] == "jpeg"
    assert (tmp_path / "out.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


# ── 검수 ──────────────────────────────────────────────────────────────
def test_parse_review():
    assert mai._parse_review('```json\n{"pass": true, "reasons": []}\n```') == {"pass": True, "reasons": []}
    assert mai._parse_review('{"pass": false, "reasons": ["글자 보임"]}')["reasons"] == ["글자 보임"]
    with pytest.raises(ValueError):
        mai._parse_review("합격입니다")
    with pytest.raises(ValueError):
        mai._parse_review('{"pass": "yes"}')


def test_review_image_sends_image_block(monkeypatch, tmp_path):
    src = tmp_path / "a.png"
    src.write_bytes(_png_bytes(tmp_path))
    sent = {}

    class _Msgs:
        def create(self, **kw):
            sent.update(kw)
            return types.SimpleNamespace(content=[types.SimpleNamespace(text='{"pass": true, "reasons": []}')])

    from services import music_lyrics
    opts = {}

    class _Client:
        messages = _Msgs()

        def with_options(self, **kw):
            opts.update(kw)
            return self

    monkeypatch.setattr(music_lyrics, "_client", lambda: _Client())
    out = mai.review_image(str(src))
    assert out["pass"] is True
    assert opts == {"timeout": 60.0, "max_retries": 0}  # 검수 60초·재시도 0
    blocks = sent["messages"][0]["content"]
    assert blocks[0]["type"] == "image" and blocks[0]["source"]["media_type"] == "image/jpeg"


def test_generate_reviewed_retry_then_pass(monkeypatch, tmp_path):
    monkeypatch.setattr(mai, "build_prompt", lambda a, avoid=None: "p")
    calls = {"gen": 0}

    def _gen(prompt, path):
        calls["gen"] += 1
        Path(path).write_bytes(b"img%d" % calls["gen"])
        return {"model": "m", "output_tokens": 1}

    verdicts = iter([{"pass": False, "reasons": ["수영복 인물"]}, {"pass": True, "reasons": []}])
    monkeypatch.setattr(mai, "generate_image", _gen)
    monkeypatch.setattr(mai, "review_image", lambda p: next(verdicts))
    res = mai.generate_reviewed("workout", str(tmp_path / "bg.png"))
    assert res["ok"] and calls["gen"] == 2
    assert Path(res["path"]).read_bytes() == b"img2"
    assert [a["pass"] for a in res["attempts"]] == [False, True]


def test_generate_reviewed_gives_up_after_three_attempts(monkeypatch, tmp_path):
    monkeypatch.setattr(mai, "build_prompt", lambda a, avoid=None: "p")
    calls = {"gen": 0}

    def _gen(prompt, path):
        calls["gen"] += 1
        if calls["gen"] == 1:
            raise RuntimeError("403 organization must be verified")
        Path(path).write_bytes(b"x")
        return {}

    monkeypatch.setattr(mai, "generate_image", _gen)
    monkeypatch.setattr(mai, "review_image", lambda p: {"pass": False, "reasons": ["글자 보임"]})
    res = mai.generate_reviewed(None, str(tmp_path / "bg.png"))
    assert res["ok"] is False and res["path"] is None and calls["gen"] == 3
    assert "403" in res["summary"] and "글자 보임" in res["summary"]
    assert not list(tmp_path.glob("*.png"))  # 불합격 후보는 남기지 않는다


# ── 렌더 정합 표식 ─────────────────────────────────────────────────────
class _FakeR2:
    """music-videos 키 → 바이트. upload/download 만 흉내."""

    def __init__(self):
        self.store: dict[str, bytes] = {}

    def install(self, monkeypatch):
        from adapters import r2_storage as r2
        monkeypatch.setattr(r2, "is_available", lambda: True)
        monkeypatch.setattr(r2, "upload_music_video",
                            lambda f, slug, name, content_type="": self.store.__setitem__(r2.music_video_key(slug, name), Path(f).read_bytes()))

        def _dl(key, dest):
            if key not in self.store:
                raise RuntimeError("404")
            Path(dest).write_bytes(self.store[key])
            return dest
        monkeypatch.setattr(r2, "download_music_object", _dl)


@pytest.fixture
def r2(monkeypatch):
    fake = _FakeR2()
    fake.install(monkeypatch)
    from services import music_channel
    monkeypatch.setattr(music_channel, "get_design_config", lambda **kw: {"play_list": {"size": 1}})
    return fake


def _row(**kw):
    base = {"slug": "s", "mix_id": "m1", "mp4_url": "https://r2/m1.mp4", "character_r2_key": None,
            "channel": "workout_music"}
    base.update(kw)
    return base


def _record(tmp_path, bg_bytes=b"BG", **kw):
    bg = tmp_path / "bg.png"
    bg.write_bytes(bg_bytes)
    vres = {"video_url": "https://r2/m1.mp4", "frame_thumb_key": "music-videos/s/m1_frame.png"}
    vres.update(kw.pop("vres", {}))
    args = dict(bg_path=str(bg), char_path=None, char_key=None, show_playlist=True, vres=vres)
    args.update(kw)
    return mai.record_render("s", "m1", **args), bg


def test_marker_match_skips(r2, tmp_path):
    ok, bg = _record(tmp_path)
    assert ok
    m = mai.matching_render(_row(), bg_path=str(bg), char_path=None, show_playlist=True)
    assert m and m["frame_thumb_key"] == "music-videos/s/m1_frame.png"


@pytest.mark.parametrize("case", ["bg", "playlist", "design", "mp4", "char", "nomarker", "noframe"])
def test_marker_mismatch_rerenders(r2, tmp_path, monkeypatch, case):
    if case == "noframe":
        ok, bg = _record(tmp_path, vres={"frame_thumb_key": None})
        assert not ok
    elif case != "nomarker":
        ok, bg = _record(tmp_path)
        assert ok
    else:
        bg = tmp_path / "bg.png"
        bg.write_bytes(b"BG")
    row, show = _row(), True
    if case == "bg":
        bg.write_bytes(b"NEW IMAGE")  # 대표가 이미지를 바꾼 뒤 재렌더 안 함
    elif case == "playlist":
        show = False
    elif case == "design":
        from services import music_channel
        monkeypatch.setattr(music_channel, "get_design_config", lambda **kw: {"play_list": {"size": 2}})
    elif case == "mp4":
        row = _row(mp4_url="https://r2/other.mp4")
    elif case == "char":
        row = _row(character_r2_key="music-characters/s/m1.png")  # 인물을 올렸는데 파일 못 받음
    assert mai.matching_render(row, bg_path=str(bg), char_path=None, show_playlist=show) is None


def test_attach_after_render_sets_thumbnail_and_marker(r2, tmp_path, monkeypatch):
    from adapters import r2_storage
    from services import music_uploads
    got = {}
    monkeypatch.setattr(r2_storage, "upload_music_thumbnail", lambda f, slug, mix: got.setdefault("up", (slug, mix)))
    monkeypatch.setattr(music_uploads, "set_thumbnail", lambda mix, key: got.setdefault("set", (mix, key)) and {"error": None})
    bg = tmp_path / "bg.png"
    bg.write_bytes(b"BG")
    out = mai.attach_after_render("s", "m1", str(bg), {"video_url": "https://r2/m1.mp4", "frame_thumb_key": "k"})
    assert out == {"thumbnail_r2_key": "music-thumbnails/s/m1.png", "error": None}
    assert got["set"] == ("m1", "music-thumbnails/s/m1.png")
    assert json.loads(r2.store["music-videos/s/m1_render.json"])["bg_sha256"]


# ── 호출부: where 는 기존 make_video 호출 그대로 ───────────────────────
def _run_manual(monkeypatch, channel, auto_image=None, image_ok=True, tmp_path=None):
    from services import music_manual, music_produce, music_video, music_viz_analyzer, music_jobs, music_uploads
    for fn in ("start_job", "update_job_step", "complete_job", "fail_job", "merge_metadata"):
        monkeypatch.setattr(music_jobs, fn, lambda *a, **k: None)
    monkeypatch.setattr(music_uploads, "set_channel", lambda *a, **k: {"stored": True})
    monkeypatch.setattr(music_produce, "produce", lambda *a, **k: {"mix": {"mix_id": "mx", "mp3_url": "u"}})
    monkeypatch.setattr(music_viz_analyzer, "analyze_song", lambda t, m: {"v": 1})
    calls = []
    monkeypatch.setattr(music_video, "make_video", lambda theme, mix, **kw: calls.append(kw) or {"video_id": "mx", "video_url": "https://r2/mx.mp4", "frame_thumb_key": "f"})
    attached = []
    monkeypatch.setattr(mai, "attach_after_render", lambda *a, **k: attached.append(a) or {"error": None})

    def _prep(job_id, action, workdir):
        if not image_ok:
            return None, {"ok": False, "summary": "1차 불합격"}
        p = Path(workdir) / "auto_bg.png"
        p.write_bytes(b"BG")
        return str(p), {"ok": True, "summary": "합격"}
    prep_calls = []
    monkeypatch.setattr(mai, "prepare_for_render", lambda *a, **k: prep_calls.append(a) or _prep(*a))
    started = music_manual.start(mood="citypop", channel=channel, auto_image=auto_image)
    music_manual.run(started["job_id"])
    return calls, attached, prep_calls, music_manual.get_status(started["job_id"])


def test_manual_where_unchanged(monkeypatch):
    calls, attached, prep, st = _run_manual(monkeypatch, None, auto_image=True)
    assert calls == [{"viz_spec": {"v": 1}, "persist": True}]  # background_path 없음 = 기존 호출 그대로
    assert not attached and not prep and "image_review" not in st and st["status"] == "done"


def test_manual_workout_single_render_with_image(monkeypatch):
    calls, attached, prep, st = _run_manual(monkeypatch, "workout_music")
    assert len(calls) == 1 and calls[0]["background_path"].endswith("auto_bg.png")
    assert attached and attached[0][:2] == (attached[0][0], "mx")
    assert st["image_review"]["ok"] is True


def test_manual_workout_image_fail_falls_back(monkeypatch):
    calls, attached, prep, st = _run_manual(monkeypatch, "workout_music", image_ok=False)
    assert calls == [{"viz_spec": {"v": 1}, "persist": True}] and not attached
    assert st["status"] == "done" and st["image_review"]["ok"] is False


def test_manual_workout_opt_out(monkeypatch):
    calls, attached, prep, st = _run_manual(monkeypatch, "workout_music", auto_image=False)
    assert not prep and calls == [{"viz_spec": {"v": 1}, "persist": True}]


# ── publish: 운동 채널만 재렌더 건너뛰기, where 는 판정 없이 항상 재렌더 ──
def _run_publish(monkeypatch, channel, match):
    from adapters import r2_storage
    from api.routes import music_dashboard as md
    from services import music_meta, music_theme, music_translate, music_uploads, music_video, youtube_upload

    row = {"slug": "s", "mix_id": "m1", "mp4_url": "https://r2/m1.mp4", "thumbnail_r2_key": "music-thumbnails/s/m1.png",
           "channel": channel, "show_playlist": None, "character_r2_key": None, "viz_spec": None}
    monkeypatch.setattr(music_uploads, "get_upload", lambda mix_id: row)
    monkeypatch.setattr(music_uploads, "get_localizations", lambda mix_id: None)
    monkeypatch.setattr(music_theme, "get_theme", lambda slug: None)
    # 공개 직전 AI 고지 검사(설명란 머리 재조립 PR) — 정상 설명란·채널 설정을 채워 둔다.
    from services import music_channel
    monkeypatch.setattr(music_channel, "get_channel_config", lambda *, channel=None: {"ai_disclosure": "AI 고지"})
    monkeypatch.setattr(md, "_ensure_localizations", lambda *a, **k: (
        {"source_lang": "ko", "meta": {"ko": {"title": "t", "description": "멘트"}}, "hashtags": ["#a"]}, [], True))
    monkeypatch.setattr(music_translate, "detect_source_lang", lambda t: "ko")
    monkeypatch.setattr(music_meta, "build_hashtags", lambda *a: ["#a"])
    monkeypatch.setattr(r2_storage, "music_mix_url", lambda *a: "u")
    monkeypatch.setattr(r2_storage, "music_mix_key", lambda *a: "k")
    monkeypatch.setattr(r2_storage, "download_music_object", lambda key, dest: Path(dest).write_bytes(b"X") and dest)
    renders, matches, uploads = [], [], []
    monkeypatch.setattr(music_video, "make_video", lambda theme, mix, **kw: renders.append(kw) or {"video_url": "https://r2/new.mp4", "frame_thumb_key": "fk"})
    monkeypatch.setattr(mai, "matching_render", lambda row, **kw: matches.append(kw) or match)
    monkeypatch.setattr(youtube_upload, "upload_music_video", lambda mp4, theme, mix, **kw: uploads.append((mp4, kw)) or {"video_id": "v", "video_url": "y"})
    monkeypatch.setattr(youtube_upload, "set_localizations", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(youtube_upload, "upload_captions", lambda *a, **k: {})
    md.publish("m1", None)
    return renders, matches, uploads


def test_publish_where_rerenders_unless_auto_marker(monkeypatch):
    # where 수동 영상: 렌더 표식이 없다(matching_render → None) → 지금처럼 항상 재렌더(회귀 0)
    for ch in ("rooftop_music", None):
        renders, matches, uploads = _run_publish(monkeypatch, ch, match=None)
        assert len(renders) == 1 and set(renders[0]) == {"background_path", "character_path", "show_playlist"}
        assert uploads[0][0] == "https://r2/new.mp4"
    # 채널 값이 없는 옛 행은 판정 자체를 하지 않는다
    _, matches, _ = _run_publish(monkeypatch, None, match={"frame_thumb_key": "x"})
    assert not matches
    # where 자동 회차 영상(자동 배경 표식 일치) → 재렌더 생략
    renders, matches, uploads = _run_publish(monkeypatch, "rooftop_music", match={"frame_thumb_key": "x"})
    assert matches and not renders


def test_publish_workout_skips_when_marker_matches(monkeypatch):
    renders, matches, uploads = _run_publish(monkeypatch, "workout_music", match={"frame_thumb_key": "music-videos/s/m1_frame.png"})
    assert matches and not renders
    assert uploads[0][0] == "https://r2/m1.mp4"
    assert uploads[0][1]["thumbnail_path"].endswith("frame.png")


def test_publish_workout_rerenders_when_unsure(monkeypatch):
    renders, matches, uploads = _run_publish(monkeypatch, "workout_music", match=None)
    assert matches and len(renders) == 1 and uploads[0][0] == "https://r2/new.mp4"


# ── 재렌더: where 는 표식 없음 / AI 이미지 불합격이면 기존 그대로 ─────────
def _rerender_env(monkeypatch, channel):
    from adapters import r2_storage
    from services import music_jobs, music_rerender, music_theme, music_uploads, music_video
    for fn in ("start_job", "update_job_step", "complete_job", "fail_job", "merge_metadata"):
        monkeypatch.setattr(music_jobs, fn, lambda *a, **k: None)
    row = {"slug": "s", "mix_id": "m1", "thumbnail_r2_key": "music-thumbnails/s/m1.png", "channel": channel,
           "show_playlist": None, "character_r2_key": None, "tag_combo": {"action": "running"}}
    monkeypatch.setattr(music_uploads, "get_upload", lambda mix_id: row)
    monkeypatch.setattr(music_theme, "get_theme", lambda slug: None)
    monkeypatch.setattr(music_rerender, "_load_mix", lambda slug, mix_id: {"mix_id": mix_id, "tracks": []})
    monkeypatch.setattr(r2_storage, "download_music_object", lambda key, dest: Path(dest).write_bytes(b"X") and dest)
    monkeypatch.setattr(r2_storage, "is_available", lambda: True)
    monkeypatch.setattr(music_video, "make_video", lambda theme, mix, **kw: {"video_url": "https://r2/m1.mp4", "frame_thumb_key": "f"})
    recorded = []
    monkeypatch.setattr(mai, "record_render", lambda *a, **k: recorded.append(k) or True)
    return music_rerender, recorded


def test_rerender_where_writes_no_marker(monkeypatch):
    rr, recorded = _rerender_env(monkeypatch, "rooftop_music")
    jid = rr.start("m1")["job_id"]
    rr.run(jid)
    assert rr.get_status(jid)["status"] == "done" and not recorded
    assert "thumbnail_url" not in rr.get_status(jid)


def test_rerender_workout_writes_marker(monkeypatch):
    rr, recorded = _rerender_env(monkeypatch, "workout_music")
    jid = rr.start("m1", channel="workout_music")["job_id"]
    rr.run(jid)
    assert rr.get_status(jid)["status"] == "done" and recorded and recorded[0]["show_playlist"] is True


def test_ai_image_fail_keeps_existing_and_releases_lock(monkeypatch):
    from services import music_uploads
    rr, recorded = _rerender_env(monkeypatch, "workout_music")
    touched = []
    monkeypatch.setattr(music_uploads, "set_thumbnail", lambda *a: touched.append(a) or {"error": None})
    monkeypatch.setattr(music_uploads, "clear_localizations", lambda *a: touched.append(a) or {"error": None})
    monkeypatch.setattr(mai, "prepare_for_render", lambda *a, **k: (None, {"ok": False, "summary": "1차 불합격: 글자 보임"}))
    jid = rr.start("m1", channel="workout_music")["job_id"]
    rr.run_with_ai_image(jid)
    st = rr.get_status(jid)
    assert st["status"] == "error" and "글자 보임" in st["error"]
    assert not touched and not recorded and "m1" not in rr._active


def test_ai_image_pass_replaces_then_rerenders(monkeypatch):
    from adapters import r2_storage
    from services import music_uploads
    rr, recorded = _rerender_env(monkeypatch, "workout_music")
    calls = []
    monkeypatch.setattr(r2_storage, "upload_music_thumbnail", lambda f, slug, mix: calls.append(("up", slug, mix)))
    monkeypatch.setattr(music_uploads, "set_thumbnail", lambda *a: calls.append(("set",) + a) or {"error": None})
    monkeypatch.setattr(music_uploads, "clear_localizations", lambda *a: calls.append(("clear",) + a) or {"error": None})

    def _prep(job_id, action, workdir, **kw):
        assert action == "running" and kw == {"reuse": False}  # 다시 만들기는 옛 이미지로 바꾸지 않는다
        p = Path(workdir) / "auto_bg.png"
        p.write_bytes(b"BG")
        return str(p), {"ok": True}
    monkeypatch.setattr(mai, "prepare_for_render", _prep)
    jid = rr.start("m1", channel="workout_music")["job_id"]
    rr.run_with_ai_image(jid)
    st = rr.get_status(jid)
    assert st["status"] == "done" and "?v=" in st["thumbnail_url"]
    assert [c[0] for c in calls] == ["up", "set", "clear"] and recorded
