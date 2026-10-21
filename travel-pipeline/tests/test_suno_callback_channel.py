"""Suno 콜백이 운동 곡의 채널을 where 로 덮어쓰지 않는지(채널 쿼리 전달·채널 모르면 키 생략)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import music_store, music_suno  # noqa: E402


def test_callback_url_carries_channel(monkeypatch):
    monkeypatch.setenv("MUSIC_CALLBACK_BASE_URL", "https://api.example.com")
    assert music_suno.callback_url("s 1", "workout_music") == \
        "https://api.example.com/api/music/suno-callback?theme_slug=s%201&channel=workout_music"
    assert music_suno.callback_url("s") == "https://api.example.com/api/music/suno-callback?theme_slug=s"
    body = music_suno._build_body({"theme_slug": "s", "instrumental": True, "style": "x", "channel": "workout_music"})
    assert body["callBackUrl"].endswith("channel=workout_music")


def test_generate_and_store_sends_channel_to_callback(monkeypatch):
    seen = {}
    monkeypatch.setattr(music_suno, "submit_generation", lambda theme: seen.update(theme) or "t1")
    monkeypatch.setattr(music_suno, "poll_task", lambda *a, **k: [])
    monkeypatch.setattr(music_suno, "store_with_retry", lambda *a, **k: [])
    theme = {"theme_slug": "s", "instrumental": True}
    music_suno.generate_and_store(theme, channel="workout_music")
    assert seen["channel"] == "workout_music" and "channel" not in theme          # 원본 dict 무변경


def _capture(monkeypatch):
    sent = []

    class _R:
        def raise_for_status(self):
            return None

    class _C:
        def __init__(self, *a, **k): ...
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            sent.append(json[0])
            return _R()
    monkeypatch.setattr(music_store, "_supabase_cfg", lambda: ("https://db", "k"))
    monkeypatch.setattr(music_store.httpx, "Client", _C)
    return sent


def test_upsert_fill_channel(monkeypatch):
    sent = _capture(monkeypatch)
    music_store.upsert_track({"id": "a"})                                      # 기존 동작: 기본 채널로 채움
    music_store.upsert_track({"id": "b"}, fill_channel=False)                  # 콜백: 채널 키 생략
    music_store.upsert_track({"id": "c", "channel": "workout_music"}, fill_channel=False)
    assert sent[0]["channel"] == "rooftop_music"
    assert "channel" not in sent[1]
    assert sent[2]["channel"] == "workout_music"


def test_store_tracks_callback_paths(monkeypatch):
    calls = []
    monkeypatch.setattr(music_store, "upsert_track", lambda rec, **kw: calls.append((rec, kw)) or {"stored": True})
    monkeypatch.setattr(music_suno.r2_storage, "music_exists", lambda *a: True)
    tr = [{"audio_id": "a", "audio_url": "u"}]
    music_suno.store_tracks("s", "t", tr, keep_channel=True)                   # 채널 모르는 콜백
    music_suno.store_tracks("s", "t", tr, channel="workout_music", keep_channel=False)  # 채널 실린 콜백
    music_suno.store_tracks("s", "t", tr)                                      # 폴링(기존)
    assert "channel" not in calls[0][0] and calls[0][1] == {"fill_channel": False}
    assert calls[1][0]["channel"] == "workout_music" and calls[1][1] == {"fill_channel": True}
    assert calls[2][1] == {"fill_channel": True}


def test_callback_route_passes_channel(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes import music
    got = []
    monkeypatch.setattr(music.music_suno, "store_tracks", lambda *a, **k: got.append(k) or [1])
    app = FastAPI()
    app.include_router(music.router, prefix="/api/music")
    c = TestClient(app)
    body = {"data": {"callbackType": "complete", "task_id": "t", "data": [{"audio_id": "a", "audio_url": "u"}]}}
    assert c.post("/api/music/suno-callback?theme_slug=s&channel=workout_music", json=body).json()["stored"] == 1
    assert c.post("/api/music/suno-callback?theme_slug=s", json=body).json()["stored"] == 1
    assert got[0] == {"channel": "workout_music", "keep_channel": False}
    assert got[1] == {"channel": None, "keep_channel": True}
