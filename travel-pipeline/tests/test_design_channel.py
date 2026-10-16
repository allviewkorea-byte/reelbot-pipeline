"""채널별 디자인(design_config) — make_video·디자인 API·렌더 표식 해시가 같은 채널을 보는지(외부 호출 없음)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import music_channel  # noqa: E402

DB = {
    "rooftop_music": {"playlist_text": "where;_____", "where_text": ""},
    "workout_music": {"playlist_text": "GYM;_____", "where_text": ""},
}


@pytest.fixture
def design_db(monkeypatch):
    calls: list = []
    saved: list = []

    def fake_get(*, channel=None):
        calls.append(channel)
        return DB[music_channel.resolve_channel(channel)]

    def fake_set(cfg, *, channel=None):
        saved.append((channel, cfg))
        return {"ok": True, "error": None}

    monkeypatch.setattr(music_channel, "get_design_config", fake_get)
    monkeypatch.setattr(music_channel, "set_design_config", fake_set)
    return calls, saved


def _render_design(monkeypatch, theme):
    from services import music_video as mv, music_meta
    monkeypatch.setattr(mv, "_require_ffmpeg", lambda: None)
    monkeypatch.setattr(mv, "_fetch", lambda src, dest: Path(dest).write_bytes(b"x"))
    monkeypatch.setattr(mv, "_duration", lambda p: 60.0)
    monkeypatch.setattr(mv, "generate_background", lambda theme, out, force=False: out)
    monkeypatch.setattr(mv, "remotion_enabled", lambda: True)
    monkeypatch.setattr(mv.r2_storage, "is_available", lambda: False)
    monkeypatch.setattr(music_meta, "generate_track_quotes", lambda tracks, theme: [])
    cap = {}

    def fake_render(bg, audio, out, **kw):
        cap["design"] = kw.get("design_config")
        raise RuntimeError("stop")  # → ffmpeg 폴백(스텁)
    monkeypatch.setattr(mv, "_render_remotion", fake_render)
    monkeypatch.setattr(mv, "compose_video", lambda *a, **k: a[2])
    mv.make_video(theme, {"mix_id": "m", "mp3_url": "/tmp/x.mp3", "tracks": []}, viz_spec={}, persist=False)
    return cap["design"]


@pytest.mark.parametrize("channel,expected", [
    (None, "where;_____"), ("rooftop_music", "where;_____"), ("workout_music", "GYM;_____"),
])
def test_make_video_uses_theme_channel_design(design_db, monkeypatch, channel, expected):
    theme = {"slug": "s", "title_kr": "t"}
    if channel:
        theme["channel"] = channel
    assert _render_design(monkeypatch, theme)["playlist_text"] == expected


def test_design_api_channel_routing(design_db):
    from fastapi.testclient import TestClient
    from api.server import app
    calls, saved = design_db
    c = TestClient(app)
    assert c.get("/api/music/design-config").json()["design_config"]["playlist_text"] == "where;_____"
    assert c.get("/api/music/design-config?channel=workout_music").json()["design_config"]["playlist_text"] == "GYM;_____"
    assert c.get("/api/music/design-config?channel=typo").status_code == 400  # 오타가 where 로 새지 않게
    r = c.post("/api/music/design-config?channel=workout_music", json={"playlist_text": "GYM;_____"})
    assert r.status_code == 200 and saved[-1][0] == "workout_music"
    r = c.post("/api/music/design-config", json={"playlist_text": "where;_____"})
    assert r.status_code == 200 and saved[-1][0] is None  # 미지정 → where(현행)
    assert c.post("/api/music/design-config?channel=nope", json={}).status_code == 400


def test_render_marker_design_hash_is_channel_specific(design_db):
    from services import music_auto_image as mai
    assert mai._design_hash("workout_music") != mai._design_hash(None)
    assert mai._design_hash(None) == mai._design_hash("rooftop_music")
