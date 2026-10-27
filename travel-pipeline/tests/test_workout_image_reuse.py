"""운동 배경 이미지 — 불합격 사유 반영 재생성(최대 3회) + 합격본 재사용(외부 호출 없음)."""

from __future__ import annotations

import io
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import music_auto_image as mai  # noqa: E402


class _FakeS3:
    """list_objects_v2 / get·put_object / download_file 만 흉내낸 R2 클라이언트."""

    def __init__(self):
        self.objs: dict[str, tuple[bytes, datetime]] = {}

    def add(self, key, data=b"PNG", days_ago=0.0):
        self.objs[key] = (data, datetime.now(timezone.utc) - timedelta(days=days_ago))

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        fake = self

        class _P:
            def paginate(self, Bucket, Prefix):
                return [{"Contents": [{"Key": k, "LastModified": lm}
                                      for k, (_, lm) in fake.objs.items() if k.startswith(Prefix)]}]
        return _P()

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self.add(Key, Body)

    def get_object(self, Bucket, Key):
        if Key not in self.objs:
            raise KeyError(Key)
        return {"Body": io.BytesIO(self.objs[Key][0])}

    def download_file(self, bucket, key, dest):
        Path(dest).write_bytes(self.objs[key][0])


@pytest.fixture
def s3(monkeypatch):
    from adapters import r2_storage
    fake = _FakeS3()
    monkeypatch.setattr(r2_storage, "is_available", lambda: True)
    monkeypatch.setattr(r2_storage, "_get_client", lambda: fake)
    monkeypatch.setattr(r2_storage, "upload_image",
                        lambda path, key, **kw: fake.add(key, Path(path).read_bytes()) or f"https://r2/{key}")
    meta: dict = {}
    from services import music_jobs
    monkeypatch.setattr(music_jobs, "merge_metadata", lambda job_id, m: meta.update(m))
    fake.meta = meta
    return fake


def _gen_and_review(monkeypatch, verdicts):
    """generate_image 는 받은 프롬프트를 기록, review_image 는 verdicts 를 차례로 돌려준다."""
    from services import music_image_prompts as mip
    monkeypatch.setattr(mip, "_generate_workout_prompt", lambda ex: (_ for _ in ()).throw(RuntimeError("no llm")))
    prompts: list[str] = []

    def _gen(prompt, path):
        prompts.append(prompt)
        Path(path).write_bytes(b"NEW%d" % len(prompts))
        return {"model": "m"}
    it = iter(verdicts)
    monkeypatch.setattr(mai, "generate_image", _gen)
    monkeypatch.setattr(mai, "review_image", lambda p: next(it))
    return prompts


def test_reject_reasons_are_fed_into_next_prompt(monkeypatch, tmp_path):
    prompts = _gen_and_review(monkeypatch, [
        {"pass": False, "reasons": ["크롭탑+반바지, 몸매 강조"]},
        {"pass": False, "reasons": ["출입구 외부 간판 문구", "화면 중앙 과노출"]},
        {"pass": True, "reasons": []},
    ])
    res = mai.generate_reviewed("workout", str(tmp_path / "bg.png"))
    assert res["ok"] and len(prompts) == 3 and Path(res["path"]).read_bytes() == b"NEW3"
    assert "반드시 피할 것" not in prompts[0]
    assert "이번엔 반드시 피할 것" in prompts[1] and "크롭탑+반바지, 몸매 강조" in prompts[1]
    assert all(r in prompts[2] for r in ("크롭탑+반바지, 몸매 강조", "출입구 외부 간판 문구", "화면 중앙 과노출"))
    assert res["attempts"][2]["avoid"] == ["크롭탑+반바지, 몸매 강조", "출입구 외부 간판 문구", "화면 중앙 과노출"]


def test_pass_is_archived_by_axis(monkeypatch, tmp_path, s3):
    _gen_and_review(monkeypatch, [{"pass": True, "reasons": []}])
    path, summary = mai.prepare_for_render("j1", "running", str(tmp_path))
    assert path and summary["ok"] and "reused" not in summary
    keys = [k for k in s3.objs if k.startswith("music-auto-bg/cardio/")]
    assert len(keys) == 1 and keys[0].endswith(".png")
    assert s3.objs["music-auto-bg/_last_cardio.txt"][0].decode() == keys[0]  # 직전 영상 배경으로 기록


def test_three_fails_reuse_same_axis_recent_and_not_last(monkeypatch, tmp_path, s3):
    s3.add("music-auto-bg/strength/a.png", b"A", days_ago=1)
    s3.add("music-auto-bg/strength/b.png", b"B", days_ago=2)
    s3.add("music-auto-bg/strength/old.png", b"OLD", days_ago=31)   # 30일 넘음 → 제외
    s3.add("music-auto-bg/cardio/c.png", b"C", days_ago=1)          # 다른 축 → 제외
    s3.add("music-auto-bg/_last_strength.txt", b"music-auto-bg/strength/a.png")  # 직전 영상 → 제외
    for _ in range(5):
        _gen_and_review(monkeypatch, [{"pass": False, "reasons": ["글자"]}] * 4)
        path, summary = mai.prepare_for_render("j1", "workout", str(tmp_path))
        assert Path(path).read_bytes() == b"B"
        s3.add("music-auto-bg/_last_strength.txt", b"music-auto-bg/strength/a.png")
    assert summary["ok"] is True and summary["reused"]["key"] == "music-auto-bg/strength/b.png"
    assert summary["reused"]["avoided_last"] is True
    assert "합격본 재사용" in summary["summary"] and "글자" in summary["summary"]
    assert len(summary["attempts"]) == 4  # 인물 2 + 인물 없음 2
    assert s3.meta["auto_image"]["reused"]["key"] == "music-auto-bg/strength/b.png"  # job metadata


def test_reuse_alternates_and_writes_last(monkeypatch, tmp_path, s3):
    s3.add("music-auto-bg/warmup/a.png", b"A", days_ago=1)
    s3.add("music-auto-bg/warmup/b.png", b"B", days_ago=1)
    seen = []
    for _ in range(4):
        _gen_and_review(monkeypatch, [{"pass": False, "reasons": ["어두움"]}] * 4)
        path, _ = mai.prepare_for_render("j", "yoga", str(tmp_path))
        seen.append(Path(path).read_bytes())
    assert all(x != y for x, y in zip(seen, seen[1:]))  # 직전과 같은 것은 피한다


def test_only_last_candidate_is_still_used(monkeypatch, tmp_path, s3):
    _gen_and_review(monkeypatch, [{"pass": False, "reasons": ["글자"]}] * 4)
    s3.add("music-auto-bg/strength/a.png", b"A")
    s3.add("music-auto-bg/_last_strength.txt", b"music-auto-bg/strength/a.png")
    path, summary = mai.prepare_for_render("j", None, str(tmp_path))
    assert Path(path).read_bytes() == b"A" and summary["reused"]["avoided_last"] is False


def test_no_archive_falls_back_to_black(monkeypatch, tmp_path, s3):
    _gen_and_review(monkeypatch, [{"pass": False, "reasons": ["글자"]}] * 4)
    s3.add("music-auto-bg/strength/old.png", b"OLD", days_ago=40)
    path, summary = mai.prepare_for_render("j", "workout", str(tmp_path))
    assert path is None and summary["ok"] is False and "reused" not in summary


def test_reuse_false_keeps_failure(monkeypatch, tmp_path, s3):
    _gen_and_review(monkeypatch, [{"pass": False, "reasons": ["글자"]}] * 4)
    s3.add("music-auto-bg/strength/a.png", b"A")
    path, summary = mai.prepare_for_render("j", "workout", str(tmp_path), reuse=False)
    assert path is None and summary["ok"] is False


def test_timeout_also_reuses(monkeypatch, tmp_path, s3):
    s3.add("music-auto-bg/strength/a.png", b"A")
    monkeypatch.setattr(mai, "prepare_timeout_sec", lambda: 0.2)
    monkeypatch.setattr(mai, "generate_reviewed", lambda *a, **k: time.sleep(2))
    path, summary = mai.prepare_for_render("j", "workout", str(tmp_path))
    assert Path(path).read_bytes() == b"A" and "시간 초과" in summary["summary"]


def test_people_fail_then_no_people_scene_passes(monkeypatch, tmp_path, s3):
    """2026-10-27: 인물 2회 불합격(크롭탑) → 3회차는 인물 없는 장면, 합격하면 재사용 없이 새 배경."""
    prompts = _gen_and_review(monkeypatch, [
        {"pass": False, "reasons": ["크롭탑"]},
        {"pass": False, "reasons": ["스포츠브라 단독"]},
        {"pass": True, "reasons": []},
    ])
    path, summary = mai.prepare_for_render("j1", "stretching", str(tmp_path))
    assert path and summary["ok"] and "reused" not in summary
    assert "사람이 한 명도 없다" not in prompts[0] and "사람이 한 명도 없다" not in prompts[1]
    assert "사람이 한 명도 없다" in prompts[2]
    assert [bool(a.get("no_people")) for a in summary["attempts"]] == [False, False, True]
    keys = [k for k in s3.objs if k.startswith("music-auto-bg/warmup/") and k.endswith(".png")]
    assert len(keys) == 1  # 인물 없는 합격본도 축별 보관


def test_people_prompt_names_concrete_outfit(monkeypatch, tmp_path):
    from services import music_image_prompts as mip
    prompts = _gen_and_review(monkeypatch, [{"pass": True, "reasons": []}])
    mai.generate_reviewed("workout", str(tmp_path / "bg.png"))
    assert any(o in prompts[0] for o in mip.WORKOUT_OUTFITS)
    assert "크롭탑·스포츠브라·민소매 크롭 금지" in prompts[0]
    assert "탱크탑" not in mip.WORKOUT_TONE
