"""공개 직전 설명란 머리 재조립 + AI 고지 필수 검사(외부 호출 없음)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import music_meta  # noqa: E402
from services.music_i18n import fixed_outro  # noqa: E402

AI = "💿 모든 음악은 AI 음원 생성 시스템으로 제작한 창작 사운드입니다."
THEME = {"slug": "s", "title_kr": "t", "channel": "workout_music"}
VIZ = {"location_en": "Seoul"}


def _parts(cfg, intro="멘트"):
    return {
        "intro": intro,
        "tracklist": "🎵 Track list\n\n00:00 A\n03:50 B",
        "info_head": music_meta.build_info_head(THEME, VIZ, cfg),
        "copyright": music_meta.build_copyright(THEME),
    }


@pytest.mark.parametrize("lang", ["ko", "en", "ja"])
def test_rebuild_is_idempotent(lang):
    p = _parts({"ai_disclosure": AI})
    desc = music_meta.assemble_description(p, lang) + "\n\n#tag1 #tag2"
    assert music_meta.rebuild_description_head(desc, lang, p["info_head"], p["copyright"]) == desc


def test_rebuild_adds_ai_to_render_time_cache_and_keeps_rest():
    old = _parts(None, intro="[en] translated intro")   # make_video 는 config=None 으로 만든다
    desc = music_meta.assemble_description(old, "en") + "\n\n#tag1"
    assert AI not in desc
    new_head = music_meta.build_info_head(THEME, VIZ, {"ai_disclosure": AI, "instagram": "gym"})
    out = music_meta.rebuild_description_head(desc, "en", new_head, old["copyright"])
    assert AI in out and "📸 Instagram: @gym" in out
    assert out.startswith("[en] translated intro")           # 번역 멘트 유지
    assert "00:00 A" in out and fixed_outro("en") in out      # 트랙리스트·안내문 유지
    assert out.endswith("#tag1")                               # 해시태그 유지


def test_rebuild_falls_back_when_head_block_was_hand_edited():
    desc = "손으로 고친 멘트\n\n" + "━" * 20 + "\n\n🎵 Track list\n\n00:00 A\n\n" + "━" * 20 + "\n\n자유 문구만 남김"
    head = music_meta.build_info_head(THEME, VIZ, {"ai_disclosure": AI})
    out = music_meta.rebuild_description_head(desc, "ko", head, "Copyright Ⓒ X All rights reserved.")
    assert out.startswith("손으로 고친 멘트") and AI in out and "00:00 A" in out


def _publish(monkeypatch, *, ai):
    import json
    from adapters import r2_storage
    from api.routes import music_dashboard as md
    from services import music_channel, music_theme, music_uploads, music_video, youtube_upload
    monkeypatch.setattr(music_channel, "get_channel_config", lambda *, channel=None: {"ai_disclosure": ai})
    head = music_meta.build_info_head(THEME, VIZ, None)  # 렌더 시점 캐시(AI 없음)
    meta = {lng: {"title": "t", "description": music_meta.assemble_description(
        {"intro": "i", "tracklist": "", "info_head": head, "copyright": "Copyright Ⓒ X All rights reserved."}, lng)}
        for lng in ("ko", "en")}
    loc = {"source_lang": "ko", "meta": meta, "lyrics": {}, "hashtags": ["#a"]}
    row = {"slug": "s", "mix_id": "m1", "mp4_url": "u", "thumbnail_r2_key": "k", "channel": "workout_music",
           "viz_spec": VIZ, "show_playlist": None, "character_r2_key": None}
    monkeypatch.setattr(music_uploads, "get_upload", lambda m: row)
    monkeypatch.setattr(music_uploads, "get_localizations", lambda m: loc)
    monkeypatch.setattr(music_uploads, "set_localizations", lambda m, l: {"stored": True})
    monkeypatch.setattr(md, "_ensure_localizations", lambda *a, **k: (loc, [], True))
    monkeypatch.setattr(music_theme, "get_theme", lambda s: None)
    monkeypatch.setattr(r2_storage, "music_mix_url", lambda *a: "u")
    monkeypatch.setattr(r2_storage, "music_mix_key", lambda *a: "k")
    monkeypatch.setattr(r2_storage, "download_music_object", lambda key, dest: Path(dest).write_text(json.dumps({})) and dest)
    monkeypatch.setattr(music_video, "make_video", lambda *a, **k: {"video_url": "n", "frame_thumb_key": None})
    up = {}
    monkeypatch.setattr(youtube_upload, "upload_music_video", lambda *a, **k: up.update(k) or {"video_id": "v", "video_url": "y"})
    monkeypatch.setattr(youtube_upload, "set_localizations", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(youtube_upload, "upload_captions", lambda *a, **k: {})
    md.publish("m1", None)
    return up


def test_publish_rebuilds_head_from_channel_config(monkeypatch):
    up = _publish(monkeypatch, ai=AI)
    assert AI in up["description"]


def test_publish_aborts_without_ai_disclosure(monkeypatch):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        _publish(monkeypatch, ai="")
    assert ei.value.status_code == 500 and "AI 고지" in ei.value.detail


@pytest.mark.parametrize("action,expected", [
    ("workout", "근력 운동 플레이리스트"), ("running", "러닝·유산소 플레이리스트"),
    ("yoga", "스트레칭·워밍업 플레이리스트"), (None, "근력 운동 플레이리스트"),
])
def test_workout_info_line_has_no_where_brand(monkeypatch, action, expected):
    monkeypatch.delenv("MUSIC_CHANNEL_NAME_WORKOUT", raising=False)
    theme = dict(THEME, tag_combo={"action": action} if action else {})
    head = music_meta.build_info_head(theme, VIZ, {"ai_disclosure": AI})
    assert head.splitlines()[0] == f"💪 2주안에몸매만들기 · {expected}"
    assert "where;" not in head
    assert music_meta.build_copyright(theme) == "Copyright Ⓒ 2주안에몸매만들기 All rights reserved."


def test_workout_channel_name_env_wins(monkeypatch):
    monkeypatch.setenv("MUSIC_CHANNEL_NAME_WORKOUT", "GYMNAME")
    assert music_meta.build_info_head(THEME, VIZ, None).startswith("💪 GYMNAME · ")


@pytest.mark.parametrize("theme", [{"slug": "s"}, {"slug": "s", "channel": "rooftop_music"}])
def test_where_info_line_unchanged(theme):
    assert music_meta.build_info_head(theme, VIZ, None).startswith("📍 where;Seoul ")
