"""자동 회차 장애 대비 — LLM 대체·이른 실패 재시도·폴백 제목·운동 배경 다양화·where 배경 폴백·실패 사유.

외부 호출(Claude·OpenAI·Suno·R2·Supabase) 없이 전부 모킹.
"""

from __future__ import annotations

import re
import random
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import anthropic  # noqa: E402

from services import music_auto_image as mai  # noqa: E402
from services import music_auto_run as ar  # noqa: E402
from services import music_llm_fallback as fb  # noqa: E402
from test_workout_image_reuse import _FakeS3  # noqa: E402

KST = ar.KST
_REQ = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _status_err(cls, code):
    return cls(f"err {code}", response=httpx.Response(code, request=_REQ), body=None)


CLAUDE_ERRORS = {
    "400_credit": lambda: _status_err(anthropic.BadRequestError, 400),
    "429": lambda: _status_err(anthropic.RateLimitError, 429),
    "529": lambda: _status_err(anthropic.APIStatusError, 529),
    "timeout": lambda: anthropic.APITimeoutError(request=_REQ),
    "connection": lambda: anthropic.APIConnectionError(request=_REQ),
}


class _FakeOpenAI:
    def __init__(self, reply="ok", fail=False):
        self.calls: list[dict] = []
        self.reply, self.fail = reply, fail
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise RuntimeError("openai down")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply))])


@pytest.fixture
def llm(monkeypatch):
    """Claude 는 항상 err 로 실패, OpenAI 는 가짜. 반환: (설정 함수, 가짜 OpenAI)."""
    from services import music_lyrics
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("MUSIC_LLM_FALLBACK", raising=False)
    for k in ("MUSIC_LLM_FALLBACK_MODEL", "MUSIC_LLM_FALLBACK_LYRICS_MODEL", "MUSIC_LLM_FALLBACK_VISION_MODEL"):
        monkeypatch.delenv(k, raising=False)
    box = {"err": CLAUDE_ERRORS["400_credit"], "openai": _FakeOpenAI()}

    def _create(**kw):
        raise box["err"]()

    claude = SimpleNamespace(messages=SimpleNamespace(create=_create))
    claude.with_options = lambda **kw: claude
    monkeypatch.setattr(music_lyrics, "_client", lambda: claude)
    monkeypatch.setattr(fb, "_client", lambda: box["openai"])
    return box


# ── A LLM 이중화 ──────────────────────────────────────────────────────
@pytest.mark.parametrize("kind", sorted(CLAUDE_ERRORS))
def test_lyrics_write_falls_back_to_openai(llm, kind, caplog):
    from services import music_lyrics
    llm["err"] = CLAUDE_ERRORS[kind]
    llm["openai"].reply = "[Verse]\n가사"
    out = music_lyrics._call("sys", "user", max_tokens=2400, task="lyrics_write", strong=True)
    assert out == "[Verse]\n가사"
    call = llm["openai"].calls[0]
    assert call["model"] == "gpt-4o" and call["messages"][0] == {"role": "system", "content": "sys"}
    assert any("[llm-fallback]" in r.getMessage() and "lyrics_write" in r.getMessage() for r in caplog.records)


def test_lyrics_review_and_plan_models(llm):
    from services import music_lyrics
    llm["openai"].reply = '{"scores":{"depth":9,"resonance":9,"monotony":9,"cliche":9},"lyrics":"x"}'
    music_lyrics._call("s", "u", task="lyrics_review", strong=True)
    music_lyrics._call("s", "u", task="lyrics_plan")
    assert [c["model"] for c in llm["openai"].calls] == ["gpt-4o", "gpt-4o-mini"]


def test_env_overrides_models(llm, monkeypatch):
    from services import music_lyrics
    monkeypatch.setenv("MUSIC_LLM_FALLBACK_MODEL", "gpt-x-mini")
    monkeypatch.setenv("MUSIC_LLM_FALLBACK_LYRICS_MODEL", "gpt-x")
    music_lyrics._call("s", "u")
    music_lyrics._call("s", "u", strong=True)
    assert [c["model"] for c in llm["openai"].calls] == ["gpt-x-mini", "gpt-x"]


def test_title_falls_back_to_openai(llm):
    from services import music_meta
    llm["openai"].reply = "운동할 때 듣는 힙합 | workout hip hop"
    ko, en = music_meta._generate_title_copy_tag({"slug": "s", "channel": "workout_music",
                                                  "tag_combo": {"action": "workout", "genre": ["hiphop"]}})
    assert (ko, en) == ("운동할 때 듣는 힙합", "workout hip hop")
    assert llm["openai"].calls[0]["model"] == "gpt-4o-mini"


def test_image_review_falls_back_with_same_criteria(llm, monkeypatch, tmp_path):
    from services import music_where_image as mwi
    monkeypatch.setattr(mai, "_review_copy", lambda src, dest: Path(dest).write_bytes(b"jpg") and dest)
    llm["openai"].reply = '{"pass": false, "reasons": ["간판 글자"]}'
    img = tmp_path / "a.png"
    img.write_bytes(b"png")
    out = mai.review_image(str(img), mwi.REVIEW_SYSTEM)
    assert out == {"pass": False, "reasons": ["간판 글자"], "model": "gpt-4o"}
    call = llm["openai"].calls[0]
    assert call["messages"][0]["content"] == mwi.REVIEW_SYSTEM                     # 기준 완화 없음
    assert call["messages"][1]["content"][0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    # 운동 검수(기본 기준)도 같은 기준 그대로
    mai.review_image(str(img))
    assert llm["openai"].calls[1]["messages"][0]["content"] == mai._REVIEW_SYSTEM


def test_off_keeps_existing_behavior(llm, monkeypatch):
    from services import music_lyrics, music_meta
    monkeypatch.setenv("MUSIC_LLM_FALLBACK", "off")
    with pytest.raises(anthropic.BadRequestError):
        music_lyrics._call("s", "u")
    ko, _ = music_meta._generate_title_copy_tag({"slug": "s", "channel": "workout_music",
                                                 "tag_combo": {"action": "workout"}})
    assert ko in music_meta._WORKOUT_INFO_COPY["strength"]                          # 기존처럼 폴백 제목
    assert llm["openai"].calls == []


def test_no_openai_key_means_no_fallback(llm, monkeypatch):
    from services import music_lyrics
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(anthropic.BadRequestError):
        music_lyrics._call("s", "u")


def test_non_api_errors_are_not_replaced(llm, monkeypatch):
    """응답 내용 문제(JSON 파싱 등)·SDK 외 예외는 대체하지 않는다."""
    from services import music_lyrics
    llm["err"] = lambda: ValueError("bad")
    with pytest.raises(ValueError):
        music_lyrics._call("s", "u")
    assert llm["openai"].calls == []


def test_both_fail_is_llm_unavailable(llm):
    from services import music_lyrics, music_manual
    llm["openai"].fail = True
    with pytest.raises(fb.FallbackFailed) as ei:
        music_lyrics._call("s", "u", task="lyrics_plan")
    assert fb.is_llm_unavailable(ei.value)
    assert music_manual.fail_reason_of(ei.value, suno_called=False) == "llm_unavailable"
    wrapped = RuntimeError("가사 생성 실패")
    wrapped.__cause__ = ei.value
    assert music_manual.fail_reason_of(wrapped, suno_called=False) == "llm_unavailable"


# ── B 이른 실패 재시도 ─────────────────────────────────────────────────
class _Jobs:
    """claim/get/reclaim/reclaim_failed/merge/show_failed 를 DB 처럼(job_id unique, 조건부 PATCH)."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.n = 0

    def _stamp(self):
        self.n += 1
        return f"2026-10-19T00:00:{self.n:02d}+00:00"

    def claim_job(self, job_id, job_type, *, channel=None, metadata=None):
        if job_id in self.rows:
            return False
        self.rows[job_id] = {"job_id": job_id, "status": "queued", "metadata": dict(metadata or {}),
                             "updated_at": self._stamp()}
        return True

    def get_job(self, job_id):
        return self.rows.get(job_id)

    def reclaim_job(self, job_id, old):
        return False

    def reclaim_failed_job(self, job_id, old, metadata):
        row = self.rows.get(job_id)
        if row and row["status"] == "failed" and row["updated_at"] == old:
            row.update(status="queued", metadata=metadata, updated_at=self._stamp())
            return True
        return False

    def merge_metadata(self, job_id, extra):
        row = self.rows[job_id]
        row["metadata"] = {**row["metadata"], **extra}
        row["updated_at"] = self._stamp()

    def show_failed(self, job_id, err):
        self.rows[job_id].update(status="failed", error_message=err, updated_at=self._stamp())


@pytest.fixture
def rjobs(monkeypatch):
    from services import music_jobs, music_recovery
    jobs = _Jobs()
    for name in ("claim_job", "get_job", "reclaim_job", "reclaim_failed_job", "merge_metadata", "show_failed"):
        monkeypatch.setattr(music_jobs, name, getattr(jobs, name))
    started: list = []

    class _T:
        def __init__(self, target, args, name, daemon):
            self.args = args

        def start(self):
            started.append(self.args)
    monkeypatch.setattr(ar.threading, "Thread", _T)
    monkeypatch.setattr(ar, "_RUNNING", set())
    monkeypatch.setattr(ar, "_SETTLED", set())

    class _HB:
        def __init__(self, *a):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(music_recovery, "Heartbeat", _HB)
    return jobs, started


def _round(minutes_to_T: float, now: datetime) -> dict:
    t = now + timedelta(minutes=minutes_to_T)
    return {"channel": "workout_music", "day": t.date(), "slot": 1, "key": "auto-workout_music-x-1",
            "publish_at": t, "start_at": t - timedelta(minutes=120)}


class _Clock:
    """ar.datetime.now 를 고정 — 재시도 시각 계산을 결정적으로."""

    def __init__(self, monkeypatch, now):
        self.now = now
        clock = self

        class _DT(datetime):
            @classmethod
            def now(cls, tz=None):
                return clock.now.astimezone(tz) if tz else clock.now
        monkeypatch.setattr(ar, "datetime", _DT)


def _fail_early(monkeypatch, reason="llm_unavailable"):
    def _boom(r, st, resume=None):
        raise ar.RoundFailed("제작 실패: LLM 대체도 실패", reason, early=True)
    monkeypatch.setattr(ar, "run_round", _boom)


def test_early_failure_retries_every_10min_max_3(rjobs, monkeypatch):
    jobs, started = rjobs
    now = datetime(2026, 10, 19, 4, 0, tzinfo=KST)
    clock = _Clock(monkeypatch, now)
    r = _round(110, now)                                   # T 까지 110분 — 3회 재시도 여유
    _fail_early(monkeypatch)
    assert ar._try_launch(r, {}, now) is True and len(started) == 1
    for i in range(1, 5):
        ar._run_round_safe(*started[-1])                    # 이번 시도 실패
        row = jobs.rows[r["key"]]
        assert row["status"] == "failed" and row["metadata"]["fail_reason"] == "llm_unavailable"
        if i <= 3:
            at = datetime.fromisoformat(row["metadata"]["retry_at"])
            assert at == clock.now + timedelta(minutes=10) and row["metadata"]["retries"] == i
            assert f"재시도 {i}/3" in row["error_message"]
            # 10분 전에는 다시 안 띄우고, 확정(SETTLED)도 하지 않는다
            assert ar._try_launch(r, {}, clock.now + timedelta(minutes=5)) is False
            assert r["key"] not in ar._SETTLED
            clock.now += timedelta(minutes=10)
            assert ar._try_launch(r, {}, clock.now) is True and len(started) == i + 1
            assert jobs.rows[r["key"]]["status"] == "queued"
            assert started[-1][2] is None                     # 재개가 아니라 새로 제작
        else:
            assert row["metadata"]["retry_at"] is None        # 3회 다 썼으면 끝
            assert ar._try_launch(r, {}, clock.now + timedelta(minutes=10)) is False
            assert r["key"] in ar._SETTLED
    assert len(started) == 4                                  # 첫 시도 + 재시도 3회


def test_retry_not_duplicated_across_instances(rjobs, monkeypatch):
    jobs, started = rjobs
    now = datetime(2026, 10, 19, 4, 0, tzinfo=KST)
    clock = _Clock(monkeypatch, now)
    r = _round(110, now)
    _fail_early(monkeypatch)
    ar._try_launch(r, {}, now)
    ar._run_round_safe(*started[-1])
    clock.now += timedelta(minutes=10)
    assert ar._try_launch(r, {}, clock.now) is True
    monkeypatch.setattr(ar, "_RUNNING", set())                # 다른 인스턴스(메모리 공유 없음)
    assert ar._try_launch(r, {}, clock.now) is False          # 조건부 PATCH 에 져서 중복 0
    assert len(started) == 2


@pytest.mark.parametrize("to_T,expect", [(25, True), (20, False), (15, False)])
def test_retry_only_if_next_try_plus_10_before_T(to_T, expect):
    now = datetime(2026, 10, 19, 4, 0, tzinfo=KST)
    assert (ar.next_retry_at(_round(to_T, now), 0, True, now) is not None) is expect


def test_retry_stops_once_past_T(rjobs, monkeypatch):
    jobs, started = rjobs
    now = datetime(2026, 10, 19, 4, 0, tzinfo=KST)
    clock = _Clock(monkeypatch, now)
    r = _round(30, now)
    _fail_early(monkeypatch)
    ar._try_launch(r, {}, now)
    ar._run_round_safe(*started[-1])
    assert jobs.rows[r["key"]]["metadata"]["retry_at"]        # 예약은 됐지만
    assert ar._try_launch(r, {}, now + timedelta(minutes=31)) is False   # T 를 넘겨 깨어나면 안 돈다
    assert r["key"] in ar._SETTLED and len(started) == 1


def test_late_failure_is_not_retried(rjobs, monkeypatch):
    """Suno 호출 뒤 실패(early=False)는 재시도하지 않는다 — 복구 A~G 몫."""
    jobs, started = rjobs
    now = datetime(2026, 10, 19, 4, 0, tzinfo=KST)
    _Clock(monkeypatch, now)
    r = _round(110, now)

    def _boom(r, st, resume=None):
        raise ar.RoundFailed("렌더 실패", "render")
    monkeypatch.setattr(ar, "run_round", _boom)
    ar._try_launch(r, {}, now)
    ar._run_round_safe(*started[-1])
    meta = jobs.rows[r["key"]]["metadata"]
    assert meta["retry_at"] is None and meta["fail_reason"] == "render" and "retries" not in meta


def test_produce_marks_early_from_manual_job(monkeypatch):
    """제작 job 이 Suno 전 실패(early_fail)면 RoundFailed.early, 사유는 제작 job 의 fail_reason."""
    from services import music_jobs, music_manual
    monkeypatch.setattr(music_jobs, "merge_metadata", lambda *a, **k: None)
    monkeypatch.setattr(ar, "_pick_image_action", lambda r: None)

    def _start(mood, tc, combo, *, channel=None, auto_image=None):
        music_manual._JOBS["je"] = {"status": "error", "error": "LLM", "fail_reason": "llm_unavailable",
                                    "early_fail": True}
        return {"ok": True, "job_id": "je"}
    monkeypatch.setattr(music_manual, "start", _start)
    monkeypatch.setattr(music_manual, "run", lambda jid: None)
    now = datetime.now(KST)
    with pytest.raises(ar.RoundFailed) as ei:
        ar._produce(_round(100, now), {"track_count": 1}, sleep=lambda s: None)
    assert ei.value.early is True and ei.value.reason == "llm_unavailable"


def test_manual_run_records_reason_and_early(monkeypatch):
    from services import music_jobs, music_manual, music_produce
    meta: dict = {}
    for name in ("fail_job", "update_job_step", "touch"):
        monkeypatch.setattr(music_jobs, name, lambda *a, **k: None)
    monkeypatch.setattr(music_jobs, "merge_metadata", lambda jid, m: meta.update(m))
    monkeypatch.setattr(music_jobs, "start_job", lambda *a, **k: k.get("job_id"))
    monkeypatch.setattr(music_produce, "produce", lambda slug, **k: (_ for _ in ()).throw(fb.FallbackFailed("x")))
    jid = music_manual.start(None, 1, None, channel=None, auto_image=False)["job_id"]
    music_manual.run(jid)
    job = music_manual._JOBS[jid]
    assert job["early_fail"] is True and job["fail_reason"] == "llm_unavailable" and meta["fail_reason"] == "llm_unavailable"

    def _after_suno(slug, **k):
        k["checkpoint"]({"type": "task", "task_id": "t1"})
        raise RuntimeError("생성 결과가 없습니다(전 곡 실패).")
    monkeypatch.setattr(music_produce, "produce", _after_suno)
    jid = music_manual.start(None, 1, None, channel=None, auto_image=False)["job_id"]
    music_manual.run(jid)
    job = music_manual._JOBS[jid]
    assert job["early_fail"] is False and job["fail_reason"] == "suno"


def test_upload_gate_reason(monkeypatch):
    from fastapi import HTTPException

    from api.routes import music_dashboard as md
    monkeypatch.setattr(md, "publish", lambda mix_id, body: (_ for _ in ()).throw(HTTPException(400, "썸네일을 먼저")))
    r = _round(100, datetime.now(KST))
    st = {"mode": "semi", "synthetic_media": False}
    with pytest.raises(ar.RoundFailed) as ei:
        ar._upload(r, st, "m")
    assert ei.value.reason == "upload_gate"
    r["image_ok"] = False
    with pytest.raises(ar.RoundFailed) as ei:
        ar._upload(r, st, "m")
    assert ei.value.reason == "image_failed"
    monkeypatch.setattr(md, "publish", lambda mix_id, body: (_ for _ in ()).throw(HTTPException(502, "yt")))
    with pytest.raises(ar.RoundFailed) as ei:
        ar._upload(r, st, "m")
    assert ei.value.reason == "upload"


# ── C 폴백 제목 ───────────────────────────────────────────────────────
_HANGUL_FIRST = re.compile(r"^[가-힣]")
_BAD_EDGE = re.compile(r"(^[\s·|,/\-]|[\s·|,/\-]$)")


@pytest.mark.parametrize("i", range(20))
def test_fallback_title_is_clean_sentence(monkeypatch, i):
    from services import music_lyrics, music_meta, music_tags
    monkeypatch.setattr(music_lyrics, "_call", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("LLM down")))
    rng = random.Random(i)
    action = rng.choice(["workout", "running", "stretching", "yoga", "confidence", "swimming"])
    combo = music_tags.smart_random({"action": action})
    theme = {"slug": f"manual_{i:012x}", "channel": "workout_music", "tag_combo": combo}
    ko, en = music_meta._generate_title_copy_tag(theme)
    assert _HANGUL_FIRST.match(ko) and not _BAD_EDGE.search(ko) and " · " not in ko, ko   # 태그 나열 아님
    assert en and en.isascii() and not _BAD_EDGE.search(en), en
    assert ko != music_tags.combo_summary_kr(combo)[:30]                             # 자르기 아님
    assert ko == music_meta._generate_title_copy_tag(theme)[0]                       # 같은 영상 = 같은 제목
    title = music_meta.build_title(theme, {})                                        # playlist🎧 {ko} | {en}
    body = title.removeprefix("playlist🎧 ")
    assert _HANGUL_FIRST.match(body) and not re.search(r"\|\s*\||^\s*\||\|\s*$", body), title
    ko_part, en_part = (x.strip() for x in body.split("|", 1))
    assert ko_part == ko and en_part.startswith(en)


@pytest.mark.parametrize("action", ["sleep", "focus", "baby_sleep", "cafe"])
def test_fallback_title_non_workout(monkeypatch, action):
    from services import music_lyrics, music_meta
    monkeypatch.setattr(music_lyrics, "_call", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("LLM down")))
    ko, en = music_meta._generate_title_copy_tag({"slug": "s", "channel": None, "tag_combo": {"action": action}})
    assert _HANGUL_FIRST.match(ko) and ko not in sum(music_meta._WORKOUT_INFO_COPY.values(), []) and en


# ── D 운동 배경 다양화 ─────────────────────────────────────────────────
@pytest.fixture
def s3(monkeypatch):
    from adapters import r2_storage
    from services import music_jobs
    fake = _FakeS3()
    monkeypatch.setattr(r2_storage, "is_available", lambda: True)
    monkeypatch.setattr(r2_storage, "_get_client", lambda: fake)
    monkeypatch.setattr(r2_storage, "upload_image",
                        lambda path, key, **kw: fake.add(key, Path(path).read_bytes()) or f"https://r2/{key}")
    monkeypatch.setattr(music_jobs, "merge_metadata", lambda *a, **k: None)
    return fake


def test_axis_distribution_100_rounds_no_three_in_a_row(s3):
    """100회차: 축 선택 → 그 축 배경 사용 기록(R2 JSON) → 다음 회차. 50/30/20 근처 + 3연속 0."""
    random.seed(11)
    seq = []
    for i in range(100):
        r = {"channel": "workout_music", "key": f"k{i}", "slot": 1, "publish_at": datetime.now(KST)}
        action = ar._pick_image_action(r)
        axis = {v: k for k, v in mai.AXIS_ACTION.items()}[action]
        mai.note_recent(axis, scene=f"scene{i}", key=f"music-auto-bg/{axis}/{i}.png")
        seq.append(axis)
    c = Counter(seq)
    assert all(not (a == b == d) for a, b, d in zip(seq, seq[1:], seq[2:]))
    assert 35 <= c["strength"] <= 62 and 18 <= c["cardio"] <= 45 and 8 <= c["warmup"] <= 32, c
    rec = mai.read_recent()
    assert len(rec["axes"]) == 10 and all(len(v) <= 10 for v in rec["scenes"].values())


def test_axis_weights_large_sample():
    rng = random.Random(3)
    c = Counter(mai.pick_workout_axis([], rng=rng) for _ in range(5000))
    assert abs(c["strength"] / 5000 - 0.5) < 0.03 and abs(c["cardio"] / 5000 - 0.3) < 0.03
    assert all(mai.pick_workout_axis(["cardio", "cardio"], rng=random.Random(i)) != "cardio" for i in range(300))


def test_where_round_has_no_workout_axis():
    assert ar._pick_image_action({"channel": "rooftop_music", "key": "k", "slot": 1,
                                  "publish_at": datetime.now(KST)}) is None


def test_axis_only_changes_background_action(monkeypatch):
    """회차 축은 배경 프롬프트 action 으로만 — 음악 조합(mood None·combo None)은 기존 그대로."""
    from services import music_jobs, music_manual
    monkeypatch.setattr(music_jobs, "merge_metadata", lambda *a, **k: None)
    monkeypatch.setattr(ar, "_pick_image_action", lambda r: "running")
    got = {}

    def _start(mood, tc, combo, *, channel=None, auto_image=None):
        got.update(mood=mood, combo=combo)
        music_manual._JOBS["jx"] = {"status": "running"}
        return {"ok": True, "job_id": "jx"}

    def _run(jid):
        got["image_action"] = music_manual._JOBS[jid].get("image_action")
        music_manual._JOBS[jid].update(status="done", mix_id="m", video_url="https://x", frame_thumb_key="f")
    monkeypatch.setattr(music_manual, "start", _start)
    monkeypatch.setattr(music_manual, "run", _run)
    ar._produce(_round(100, datetime.now(KST)), {"track_count": 1}, sleep=lambda s: None)
    assert got == {"mood": None, "combo": None, "image_action": "running"}


def _fail_all(monkeypatch, scenes_seen=None):
    from services import music_image_prompts as mip

    def _gen_prompt(examples, avoid_recent=None, **kw):
        if scenes_seen is not None:
            scenes_seen.append(list(avoid_recent or []))
        raise RuntimeError("no llm")
    monkeypatch.setattr(mip, "_generate_workout_prompt", _gen_prompt)
    monkeypatch.setattr(mai, "generate_image", lambda prompt, path: Path(path).write_bytes(b"N") and {})
    monkeypatch.setattr(mai, "review_image", lambda p: {"pass": False, "reasons": ["글자"]})


def test_reuse_excludes_recent_10(monkeypatch, tmp_path, s3):
    keys = [f"music-auto-bg/strength/{i:02d}.png" for i in range(12)]
    for k in keys:
        s3.add(k, k.encode(), days_ago=1)
    for k in keys[:10]:
        mai.note_recent("strength", key=k)
    _fail_all(monkeypatch)
    path, summary = mai.prepare_for_render("j", "workout", str(tmp_path))
    first = summary["reused"]["key"]
    assert first in keys[10:] and Path(path).read_bytes() == first.encode()         # 최근 10장 제외
    assert mai.recent_for(mai.read_recent(), "keys", "strength")[-1] == first       # 사용 기록 갱신
    path, summary = mai.prepare_for_render("j", "workout", str(tmp_path))
    assert summary["reused"]["key"] != first                                         # 방금 쓴 것도 제외


def test_reuse_all_recent_picks_least_recently_used(monkeypatch, tmp_path, s3):
    keys = [f"music-auto-bg/cardio/{i:02d}.png" for i in range(5)]
    for k in keys:
        s3.add(k, k.encode(), days_ago=1)
    for k in [keys[3], keys[1], keys[4], keys[0], keys[2]]:          # 오래된 순서로 사용
        mai.note_recent("cardio", key=k)
    _fail_all(monkeypatch)
    path, summary = mai.prepare_for_render("j", "running", str(tmp_path))
    assert summary["reused"]["key"] == keys[3]                          # 가장 오래전에 쓴 것
    assert Path(path).read_bytes() == keys[3].encode()


def test_recent_scenes_go_into_prompt_writer_and_pool_fallback(monkeypatch, tmp_path, s3):
    from services import music_image_prompts as mip
    for i in range(3):
        mai.note_recent("warmup", scene=mip.WORKOUT_IMAGE_PROMPTS["warmup"][i])
    seen: list = []
    _fail_all(monkeypatch, seen)
    prompts = []
    monkeypatch.setattr(mai, "generate_image", lambda prompt, path: prompts.append(prompt) or Path(path).write_bytes(b"N") and {})
    mai.prepare_for_render("j", "stretching", str(tmp_path))
    assert seen and seen[0] == mip.WORKOUT_IMAGE_PROMPTS["warmup"][:3]             # 최근 장면 지시
    recent = set(mip.WORKOUT_IMAGE_PROMPTS["warmup"][:3])
    assert prompts and not any(sc in p for p in prompts for sc in recent)            # 풀 폴백도 최근 제외


def test_passed_image_records_scene_and_key(monkeypatch, tmp_path, s3):
    from services import music_image_prompts as mip
    monkeypatch.setattr(mip, "_generate_workout_prompt", lambda ex, avoid_recent=None, **kw: "햇살 드는 러닝트랙 위를 달리는 러너, 낮은 앵글")
    monkeypatch.setattr(mai, "generate_image", lambda prompt, path: Path(path).write_bytes(b"N") and {})
    monkeypatch.setattr(mai, "review_image", lambda p: {"pass": True, "reasons": []})
    path, summary = mai.prepare_for_render("j", "running", str(tmp_path))
    rec = mai.read_recent()
    assert summary["ok"] and rec["axes"] == ["cardio"]
    assert rec["scenes"]["cardio"] == ["햇살 드는 러닝트랙 위를 달리는 러너, 낮은 앵글"]
    assert rec["keys"]["cardio"][0].startswith("music-auto-bg/cardio/")


# ── E where 배경 폴백 ─────────────────────────────────────────────────
WHERE = "rooftop_music"


def _where_fail(monkeypatch):
    monkeypatch.setattr(mai, "generate_reviewed", lambda *a, **k: {"ok": False, "path": None, "attempts": [],
                                                                     "summary": "전부 불합격"})


def test_where_fallback_order(monkeypatch, tmp_path, s3):
    from adapters import r2_storage
    from services import music_uploads
    _where_fail(monkeypatch)
    legacy_calls = []
    monkeypatch.setattr(music_uploads, "list_thumbnail_keys", lambda ch: legacy_calls.append(ch) or ["music-thumbnails/old/m1.png"])
    monkeypatch.setattr(r2_storage, "download_music_object", lambda key, dest: Path(dest).write_bytes(b"LEGACY") and dest)
    # ① 장르 보관함
    s3.add("music-auto-bg/where/jazz/a.png", b"JAZZ")
    s3.add("music-auto-bg/where/lofi/b.png", b"LOFI", days_ago=90)   # 기간 넘은 다른 장르(폴백에선 허용)
    path, summary = mai.prepare_for_render("j", None, str(tmp_path), channel=WHERE, genre="jazz")
    assert Path(path).read_bytes() == b"JAZZ" and "source" not in summary["reused"]
    # ② 장르 보관함 비었음 → where 전 장르 보관함
    s3.objs.pop("music-auto-bg/where/jazz/a.png")
    path, summary = mai.prepare_for_render("j", None, str(tmp_path), channel=WHERE, genre="jazz")
    assert Path(path).read_bytes() == b"LOFI" and summary["reused"]["source"] == "where_all"
    assert legacy_calls == []
    # ③ 보관함 전부 없음 → 기존 where 배경(music_uploads.thumbnail_r2_key)
    s3.objs.pop("music-auto-bg/where/lofi/b.png")
    path, summary = mai.prepare_for_render("j", None, str(tmp_path), channel=WHERE, genre="jazz")
    assert Path(path).read_bytes() == b"LEGACY" and summary["reused"]["source"] == "where_legacy"
    assert legacy_calls == [WHERE]
    # ④ 그것도 없음 → None
    monkeypatch.setattr(music_uploads, "list_thumbnail_keys", lambda ch: [])
    path, summary = mai.prepare_for_render("j", None, str(tmp_path), channel=WHERE, genre="jazz")
    assert path is None and summary["ok"] is False


def test_where_fallback_skips_deleted_legacy(monkeypatch, tmp_path, s3):
    from adapters import r2_storage
    from services import music_uploads
    _where_fail(monkeypatch)
    monkeypatch.setattr(music_uploads, "list_thumbnail_keys", lambda ch: ["gone1", "ok", "gone2"])

    def _dl(key, dest):
        if key != "ok":
            raise RuntimeError("NoSuchKey")
        Path(dest).write_bytes(b"OK")
        return dest
    monkeypatch.setattr(r2_storage, "download_music_object", _dl)
    path, summary = mai.prepare_for_render("j", None, str(tmp_path), channel=WHERE, genre="cafe")
    assert Path(path).read_bytes() == b"OK" and summary["reused"]["key"] == "ok"


def _manual_where_env(monkeypatch, bg):
    """where 자동 회차 제작(music_manual.run) — Suno·렌더·R2 모킹. bg: prepare_for_render 반환 경로."""
    from adapters import r2_storage
    from services import music_jobs, music_manual, music_produce, music_recovery, music_uploads, music_video, music_viz_analyzer
    meta: dict = {}
    for name in ("fail_job", "update_job_step", "touch", "complete_job"):
        monkeypatch.setattr(music_jobs, name, lambda *a, **k: None)
    monkeypatch.setattr(music_jobs, "merge_metadata", lambda jid, m: meta.update(m))
    monkeypatch.setattr(music_jobs, "start_job", lambda *a, **k: k.get("job_id"))

    def _produce(slug, **k):
        k["checkpoint"]({"type": "task", "task_id": "t1"})
        k["checkpoint"]({"type": "track", "record": {"audio_id": "a1", "r2_key": "k1"}})
        return {"mix": {"mix_id": "mix1", "mp3_url": "u", "tracks": []}}
    monkeypatch.setattr(music_produce, "produce", _produce)
    monkeypatch.setattr(music_viz_analyzer, "analyze_song", lambda theme, mix: {})
    renders = []
    monkeypatch.setattr(music_video, "make_video", lambda theme, mix, **k: renders.append(k) or
                        {"video_id": "mix1", "video_url": "https://r2/m.mp4", "frame_thumb_key": "f.png", "duration": 60})
    monkeypatch.setattr(music_recovery, "check_render", lambda v, channel=None: {"ok": True})
    monkeypatch.setattr(music_recovery, "recover_video", lambda *a, **k: pytest.fail("복구 C 를 타면 안 됨"))
    monkeypatch.setattr(mai, "prepare_for_render", lambda *a, **k: (bg, {"ok": bool(bg), "summary": "s"}))
    thumbs = []
    monkeypatch.setattr(r2_storage, "upload_music_thumbnail", lambda path, slug, mix_id: f"https://r2/{mix_id}.png")
    monkeypatch.setattr(music_uploads, "set_thumbnail", lambda mix_id, key: thumbs.append((mix_id, key)) or {})
    monkeypatch.setattr(music_uploads, "set_channel", lambda *a: {})
    monkeypatch.setattr(mai, "record_render", lambda *a, **k: None)
    return music_manual, meta, renders, thumbs


def test_where_no_background_stops_before_render(monkeypatch):
    mm, meta, renders, thumbs = _manual_where_env(monkeypatch, None)
    jid = mm.start("jazz", 1, None, channel=WHERE, auto_image=True)["job_id"]
    mm.run(jid)
    job = mm._JOBS[jid]
    assert job["status"] == "error" and job["fail_reason"] == "upload_gate" and meta["fail_reason"] == "upload_gate"
    assert renders == [] and thumbs == []                        # 검은 배경 렌더·발행 없음
    assert job["early_fail"] is False                             # 곡은 만들었다 → 재시도 대상 아님


def test_where_fallback_background_fills_thumbnail(monkeypatch, tmp_path):
    bg = tmp_path / "reuse_bg.png"
    bg.write_bytes(b"LOFI")
    mm, meta, renders, thumbs = _manual_where_env(monkeypatch, str(bg))
    jid = mm.start("jazz", 1, None, channel=WHERE, auto_image=True)["job_id"]
    mm.run(jid)
    job = mm._JOBS[jid]
    assert job["status"] == "done" and renders[0]["background_path"] == str(bg)
    assert len(thumbs) == 1 and thumbs[0][0] == "mix1"                                 # 썸네일 = 같은 배경 이미지
    assert thumbs[0][1].startswith("music-thumbnails/") and thumbs[0][1].endswith("/mix1.png")


def test_publish_gate_passes_with_thumbnail(monkeypatch):
    """썸네일 키가 박힌 행은 공개 게이트(thumbnail_r2_key 필수)를 통과한다 — 게이트는 그대로."""
    from api.routes import music_dashboard as md
    src = Path(md.__file__).read_text(encoding="utf-8")
    assert "썸네일을 먼저 업로드하세요(공개 업로드 게이트)" in src                    # 게이트 제거 안 함
