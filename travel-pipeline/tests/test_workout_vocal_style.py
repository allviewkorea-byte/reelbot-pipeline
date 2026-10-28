"""운동 채널 보컬 장르 고정·소재 풀·가사 톤·이미지 단계 상한 검증(외부 호출 없음)."""

from __future__ import annotations

import re
import sys
import threading
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import music_workout_style as ws  # noqa: E402

LLM = "late-night city pop, muted electric piano, mellow groove, lo-fi warmth, soft vocals, punchy drums, bright synth stabs, extended, long song"
BAD = re.compile(r"city pop|lo-fi|lofi|mellow|late-night|late night|\bsoft\b|\bchill\b|\bsad\b|melanchol", re.I)


def test_lock_starts_with_genre_and_strips_foreign():
    tag = "for workout, energetic, hip-hop, fast tempo, with vocals"
    st = ws.lock_vocal_style(tag, LLM, "workout")
    assert st.startswith("hip-hop, for workout, energetic")
    assert not BAD.search(st)
    assert "electric piano" in st and "punchy drums" in st  # 변주 꼬리는 남는다
    assert "memorable catchy melody" in st and st.endswith(ws.VOCAL_QUALITY)   # 운동 부스터 + 보컬 꼬리(2026-10-28)
    assert ", vocals," not in st                               # "soft vocals" 잔여물 제거


def test_lock_warmup_keeps_allowed_genres_but_strips_listed_words():
    st = ws.lock_vocal_style("for yoga, serene and balanced, acoustic, ambient", "acoustic guitar, mellow ambient pad, sad strings, slow build", "yoga")
    assert st.startswith("acoustic, ambient")
    assert "acoustic guitar" in st and "ambient pad" in st and "slow build" in st
    assert not re.search(r"mellow|\bsad\b", st)


def test_lock_respects_1000_chars():
    long_llm = ", ".join(f"layer{i} synth texture" for i in range(200))
    st = ws.lock_vocal_style("for workout, energetic, house", long_llm, "workout", finalize=lambda s: s + ", male vocals")
    assert len(st) <= ws.SUNO_STYLE_MAX
    assert st.startswith("house") and "BPM" in st and st.endswith(ws.VOCAL_QUALITY)  # 꼬리만 덜고 부스터·보컬 꼬리 유지


def test_lock_empty_llm_style_is_tag_plus_booster():
    st = ws.lock_vocal_style("for running, upbeat, electronic", "", "running")
    assert st.startswith("electronic, for running, upbeat") and "BPM" in st


def test_pools_and_tone():
    assert ws.subtheme_pool("workout") is None and ws.lyric_tone("workout") is None  # where
    pool = ws.subtheme_pool("running", channel="workout_music")
    assert len(pool) == 15 and "마지막 한 세트" in pool
    assert "아침 스트레칭" in ws.subtheme_pool("yoga", channel="workout_music")
    assert "우울" in ws.lyric_tone("workout", channel="workout_music")
    assert ws.lyric_tone("stretching", channel="workout_music") is None  # warmup 은 기존 톤


def test_prepare_for_render_hang_falls_back(monkeypatch, tmp_path):
    from services import music_auto_image as mai
    monkeypatch.setenv("MUSIC_IMAGE_PREPARE_TIMEOUT_SEC", "1.5")
    monkeypatch.setattr(mai, "generate_reviewed", lambda *a, **k: threading.Event().wait() or {})
    from services import music_jobs
    monkeypatch.setattr(music_jobs, "merge_metadata", lambda *a, **k: None)
    t0 = time.monotonic()
    path, summary = mai.prepare_for_render("j", "workout", str(tmp_path))
    assert path is None and "시간 초과" in summary["summary"]
    assert time.monotonic() - t0 < 5


def test_prepare_for_render_exception_falls_back(monkeypatch, tmp_path):
    from services import music_auto_image as mai, music_jobs
    monkeypatch.setattr(music_jobs, "merge_metadata", lambda *a, **k: None)
    monkeypatch.setattr(mai, "generate_reviewed", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    path, summary = mai.prepare_for_render("j", "workout", str(tmp_path))
    assert path is None and "boom" in summary["summary"]


def test_retry_skipped_when_deadline_near(monkeypatch, tmp_path):
    from services import music_auto_image as mai
    monkeypatch.setattr(mai, "build_prompt", lambda a, avoid=None: "p")
    calls = []

    def _gen(prompt, path):
        calls.append(1)
        Path(path).write_bytes(b"x")
        return {}
    monkeypatch.setattr(mai, "generate_image", _gen)
    monkeypatch.setattr(mai, "review_image", lambda p: {"pass": False, "reasons": ["글자"]})
    res = mai.generate_reviewed(None, str(tmp_path / "bg.png"), deadline=time.monotonic() + 30)
    assert len(calls) == 1 and res["attempts"][-1]["error"].startswith("시간 상한")


def test_vocal_melody_and_no_chopped_vocals():
    """2026-10-21: 보컬 곡 style 에 멜로디·이어 부르기, 운동 negativeTags 에 속사포·잘린 보컬 금지."""
    from services import music_produce as mp
    from services import music_workout_style as ws
    st = mp._vocal_style("dance-pop, energetic", "female")
    assert "catchy memorable vocal melody" in st and "legato" in st and "female vocals" in st
    long_base = "x" * 900
    assert mp._VOCAL_MELODY not in mp._vocal_style(long_base, "male")    # 1000자 넘으면 멜로디 문구만 생략
    for action in ("weight", "running", "stretching"):
        neg = ws.negative_tags(action, channel="workout_music")
        assert "rapid-fire vocals" in neg and "vocal chops" in neg
    where_neg = ws.negative_tags("weight", channel="rooftop_music")          # where: 거친 소리만(2026-10-28)
    assert "distorted" in where_neg and "clipping" in where_neg
    assert "lo-fi" not in where_neg and "mellow" not in where_neg and "vinyl" not in where_neg   # 채널 성격 유지
