"""음악 제작 자동 복구(A~G) — 체크포인트 · 렌더 검증 · 영상 재시도 · 재시작 복구 · 곡 재취득.

원칙
  - 이미 만든 곡은 Suno 로 다시 만들지 않는다. 곡의 단일 진실은 music_tracks(+R2),
    작업 상태의 단일 진실은 music_jobs.metadata.recovery(jsonb, 신규 컬럼 없음).
  - music_video.py 는 무수정. 폴백·업로드 실패 판정은 make_video **반환값**으로 호출부에서 한다.

구성
  A Checkpoint      — 작업 시작 시 주제(slug·theme·곡수)를, 곡이 저장될 때마다 track·taskId 를 누적.
  B check_render    — frame_thumb_key 없음(=Remotion 폴백) / video_url 이 http 아님 → 실패.
                      추가로 청크 구간마다 1프레임 밀착 시트를 Claude 비전 1회(60초)로 "모든 칸에
                      중앙 로고가 보이는가" 판정. 비전 호출 자체가 실패하면 그 검증만 건너뛴다.
  C recover_video   — 곡 확보 이후 단계가 실패하면 같은 곡·같은 주제·가사로 영상만 다시(최대 2회,
                      60초 간격). 같은 mix 가 있으면 같은 mix_id 로 재렌더 → 검토 큐 행이 덮어써진다.
                      최종 실패면 큐 행을 status=render_failed 로(자동 업로드 대상 제외).
  E Heartbeat / recover_stale_jobs — 진행 중 작업은 1분마다 updated_at 갱신. "updated_at 10분 경과 +
                      이 서버 시작 전" 인 queued/running 행은 끊긴 작업 → 곡이 있으면 C 경로로 재개,
                      없으면 failed("서버 재시작으로 중단")로 정리. 동시 1개(수동 생성 락 공유).
  F reacquire_pending_stores — R2 저장이 끝내 실패한 Suno taskId 를 record-info 로 다시 받아 저장.
"""

from __future__ import annotations

import base64
import json
import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

STALE_MIN = 10            # E: 하트비트가 이만큼 끊기면 끊긴 작업
HEARTBEAT_SEC = 60        # E: 진행 중 updated_at 갱신 주기
RETRY_ATTEMPTS = 2        # C: 영상 단계 재시도 횟수
RETRY_WAIT_SEC = 60       # C: 재시도 사이 대기
CHECK_TIMEOUT_SEC = 60.0  # B: 비전 검증 1회 상한
_FFMPEG_TIMEOUT = 60
_STARTED_AT = datetime.now(timezone.utc)
_RECOVERY_KEY = "recovery"


def _jobs():
    from services import music_jobs
    return music_jobs


# ── A 체크포인트 ──────────────────────────────────────────────────────
class Checkpoint:
    """작업 metadata.recovery 에 복구 정보를 누적한다(best-effort, 실패해도 제작은 계속).

    produce(checkpoint=cp) 로 넘기면 곡 이벤트({"type": "task"|"track"|"store_failed"})를 받는다.
    """

    def __init__(self, job_id: str, ctx: dict):
        self.job_id = job_id
        self.ctx = dict(ctx)          # slug·theme·track_count·minutes·channel·auto_image·kind
        self.tracks: list[dict] = []
        self.task_ids: list[str] = []
        self.pending: list[dict] = []
        self.stage = "songs"
        self.extra: dict = {}
        self._lock = threading.Lock()

    def snapshot(self) -> dict:
        return {**self.ctx, "tracks": list(self.tracks), "task_ids": list(self.task_ids),
                "pending_store": list(self.pending), "stage": self.stage,
                "requested": self.ctx.get("track_count"), **self.extra}

    def save(self) -> None:
        try:
            _jobs().merge_metadata(self.job_id, {_RECOVERY_KEY: self.snapshot()})
        except Exception as e:  # noqa: BLE001
            logger.warning("[recovery] 체크포인트 저장 실패(무시) job=%s: %s", self.job_id, e)

    def __call__(self, ev: dict) -> None:
        with self._lock:
            t = ev.get("type")
            if t == "task" and ev.get("task_id") and ev["task_id"] not in self.task_ids:
                self.task_ids.append(ev["task_id"])
            elif t == "track" and (ev.get("record") or {}).get("audio_id"):
                if ev["record"]["audio_id"] not in {x.get("audio_id") for x in self.tracks}:
                    self.tracks.append(ev["record"])
            elif t == "store_failed":
                self.pending.append({k: ev.get(k) for k in ("task_id", "slug", "genre", "action", "channel", "audio_urls")})
            else:
                return
        self.save()

    def set_stage(self, stage: str, **extra) -> None:
        with self._lock:
            self.stage = stage
            self.extra.update(extra)
        self.save()

    def update_theme(self, theme: dict) -> None:
        self.ctx["theme"] = _theme_brief(theme)
        self.save()


def _theme_brief(theme: dict) -> dict:
    """복구 재렌더에 필요한 주제 필드(제목·장르·tag_combo·채널 등) — 원래 주제를 그대로 쓰기 위함."""
    keep = ("slug", "title_kr", "title_en", "genre", "mood", "situation", "type", "style_prompt",
            "lyric_tone", "tag_combo", "channel", "genre_id", "track_count")  # genre_id: where 자동 회차
    return {k: theme.get(k) for k in keep if theme.get(k) is not None}


# ── E 하트비트 ────────────────────────────────────────────────────────
class Heartbeat:
    """진행 중 작업의 updated_at 을 HEARTBEAT_SEC 마다 갱신(Suno·렌더처럼 긴 단계 포함)."""

    def __init__(self, job_id: str, interval: float = HEARTBEAT_SEC):
        self.job_id = job_id
        self.interval = interval
        self._stop = threading.Event()
        self._th = threading.Thread(target=self._loop, name=f"hb-{job_id[:8]}", daemon=True)

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                _jobs().touch(self.job_id)
            except Exception:  # noqa: BLE001
                pass

    def __enter__(self):
        self._th.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        return False


# ── B 렌더 검증 ───────────────────────────────────────────────────────
class RenderFailed(RuntimeError):
    def __init__(self, reason: str, video: dict | None = None):
        super().__init__(reason)
        self.reason = reason
        self.video = video or {}


def _check_enabled() -> bool:
    return (os.getenv("MUSIC_RENDER_CHECK") or "on").strip().lower() not in ("0", "off", "false", "no")


def _vision_blocks() -> bool:
    """비전(밀착 시트) 판정으로 차단할지. 기본 warn — 기록만 하고 업로드를 막지 않는다.

    밝은 배경 위 흰 로고를 작은 칸에서 "없음"으로 잘못 볼 수 있어, 정확도 확인 전까지는 경고만 남긴다
    (대표 결정 2026-10-16). 로고 누락의 실제 원인(ffmpeg 폴백·비 http mp4)은 확정 신호로 계속 차단한다.
    env MUSIC_RENDER_CHECK_VISION=block 일 때만 비전 판정으로 차단.
    """
    return (os.getenv("MUSIC_RENDER_CHECK_VISION") or "warn").strip().lower() == "block"


def frame_times(duration: float) -> list[float]:
    """청크 구간마다 1프레임(구간 가운데) 시각. 렌더와 같은 청크 계획(music_video._plan_chunks)."""
    if not duration or duration <= 0:
        return []
    from services import music_video
    fps = getattr(music_video, "_FPS", 30)
    chunks = music_video._plan_chunks(duration)
    return [round(((c["start_frame"] + c["end_frame"]) / 2) / fps, 2) for c in chunks]


def build_contact_sheet(video_url: str, times: list[float], dest: str) -> str:
    """mp4(URL 가능)에서 times 마다 1프레임 → 가로 4칸 격자 JPEG 1장. 전체 다운로드 없이 시킹."""
    work = Path(tempfile.mkdtemp(prefix="rcheck_"))
    try:
        for i, t in enumerate(times, 1):
            subprocess.run(
                ["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", video_url,
                 "-frames:v", "1", "-vf", "scale=480:-2", str(work / f"f_{i:02d}.jpg")],
                check=True, capture_output=True, text=True, timeout=_FFMPEG_TIMEOUT,
            )
        cols = min(4, max(1, len(times)))
        rows = math.ceil(len(times) / cols)
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-framerate", "1", "-i", str(work / "f_%02d.jpg"),
             "-vf", f"tile={cols}x{rows}:padding=6:color=gray", "-frames:v", "1", "-q:v", "4", dest],
            check=True, capture_output=True, text=True, timeout=_FFMPEG_TIMEOUT,
        )
        return dest
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _logo_text(channel: str | None) -> str:
    try:
        from services import music_channel
        cfg = music_channel.get_design_config(channel=channel) or {}
        return str(cfg.get("playlist_text") or "").strip() or "PLAY LIST"
    except Exception:  # noqa: BLE001
        return "PLAY LIST"


_VISION_SYSTEM = (
    "너는 음악 유튜브 영상의 렌더 검수자다. 입력은 한 영상의 여러 구간에서 1프레임씩 뽑아 격자로 붙인 "
    "밀착 시트다(회색 여백으로 칸이 나뉘고, 마지막 줄 오른쪽 빈 회색 칸은 무시한다). "
    "정상 렌더는 **모든 칸의 화면 중앙에 큰 로고 텍스트**가 보인다. 로고 문구는 사용자 메시지에 준다 "
    "(밑줄 부분은 장식이라 정확히 같지 않아도 된다). 로고가 없고 배경 사진만 보이는 칸이 하나라도 있으면 "
    "실패다. 반드시 JSON 한 개만 출력한다: "
    '{"all_logo": true 또는 false, "missing_cells": [로고가 없는 칸 번호(왼쪽 위부터 1)], "note": "짧게"}'
)


def vision_logo_check(sheet_path: str, logo_text: str, cells: int) -> dict:
    """밀착 시트 → {all_logo, missing_cells, note, model}. 호출·파싱 실패는 예외."""
    from services import music_auto_image, music_lyrics

    client = music_lyrics._client().with_options(timeout=CHECK_TIMEOUT_SEC, max_retries=0)
    b64 = base64.b64encode(Path(sheet_path).read_bytes()).decode("ascii")
    model = music_auto_image.review_model()
    msg = client.messages.create(
        model=model, max_tokens=300, system=_VISION_SYSTEM,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
            {"type": "text", "text": f"로고 문구: {logo_text}\n칸 수: {cells}\nJSON 만 출력해."},
        ]}],
    )
    text = "".join(getattr(b, "text", "") for b in (msg.content or []))
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"비전 응답에 JSON 없음: {text[:120]}")
    obj = json.loads(m.group(0))
    if not isinstance(obj.get("all_logo"), bool):
        raise ValueError(f"all_logo 가 bool 아님: {obj!r}"[:160])
    return {"all_logo": obj["all_logo"], "missing_cells": list(obj.get("missing_cells") or [])[:20],
            "note": str(obj.get("note") or "")[:120], "model": model}


def check_render(video: dict | None, *, channel: str | None = None) -> dict:
    """make_video 반환값 검증 → {ok, reason, vision?}. 로그 접두사 [render-check]."""
    v = video or {}
    mix_id = v.get("video_id") or "-"
    url = str(v.get("video_url") or "")
    if not url.startswith("http"):
        out = {"ok": False, "reason": "mp4 R2 업로드 실패(로컬 경로)"}
    elif not v.get("frame_thumb_key"):
        out = {"ok": False, "reason": "Remotion 렌더 실패(ffmpeg 폴백 — 로고 없음)"}
    else:
        out = {"ok": True, "reason": ""}
        if _check_enabled():
            out["vision"] = _vision_part(url, float(v.get("duration") or 0), channel)
            if out["vision"].get("all_logo") is False:
                if _vision_blocks():
                    out = {"ok": False, "reason": f"렌더 검증 실패(로고 없음, 칸 {out['vision'].get('missing_cells')})",
                           "vision": out["vision"]}
                else:
                    out["warning"] = f"비전 검증 경고(로고 없음으로 판정, 칸 {out['vision'].get('missing_cells')}) — warn 모드라 차단 안 함"
    logger.warning("[render-check] mix_id=%s ok=%s %s%s%s", mix_id, out["ok"], out["reason"] or "정상",
                   f" vision={out.get('vision')}" if out.get("vision") else "",
                   f" ⚠️ {out['warning']}" if out.get("warning") else "")
    return out


def _vision_part(url: str, duration: float, channel: str | None) -> dict:
    times = frame_times(duration)
    if not times:
        return {"skipped": "길이 정보 없음"}
    tmp = Path(tempfile.mkdtemp(prefix="rsheet_"))
    t0 = time.monotonic()
    try:
        sheet = build_contact_sheet(url, times, str(tmp / "sheet.jpg"))
        res = vision_logo_check(sheet, _logo_text(channel), len(times))
        res["cells"] = len(times)
        res["sec"] = round(time.monotonic() - t0, 1)
        return res
    except Exception as e:  # noqa: BLE001 - 검증 자체 실패는 이 검증만 건너뜀
        logger.warning("[render-check] 밀착 시트 검증 건너뜀: %s", str(e)[:200])
        return {"skipped": str(e)[:160]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── C 영상 단계 재시도 ────────────────────────────────────────────────
def _load_mix(slug: str, mix_id: str) -> dict | None:
    """R2 믹스 JSON 으로 mix 복원(publish 와 같은 방식). 없으면 None."""
    from adapters import r2_storage
    tmp = Path(tempfile.mkdtemp(prefix="rmix_"))
    try:
        p = tmp / "mix.json"
        r2_storage.download_music_object(r2_storage.music_mix_key(slug, mix_id, "json"), str(p))
        meta = json.loads(p.read_text(encoding="utf-8"))
        return {**meta, "mix_id": mix_id, "tracks": meta.get("tracks") or [],
                "mp3_url": r2_storage.music_mix_url(slug, mix_id, "mp3")}
    except Exception as e:  # noqa: BLE001
        logger.warning("[recovery] 믹스 복원 실패 slug=%s mix=%s: %s", slug, mix_id, e)
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _load_lyrics(slug: str, audio_ids: list[str]) -> dict[str, str]:
    from adapters import r2_storage
    out: dict[str, str] = {}
    tmp = Path(tempfile.mkdtemp(prefix="rlyr_"))
    try:
        for aid in audio_ids:
            try:
                p = tmp / f"{aid}.txt"
                r2_storage.download_music_object(r2_storage.lyrics_key(slug, aid), str(p))
                txt = p.read_text(encoding="utf-8").strip()
                if txt:
                    out[aid] = txt
            except Exception:  # noqa: BLE001 - 연주곡·누락은 가사 없이
                pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def rebuild_mix(rec: dict) -> dict:
    """체크포인트의 곡으로 마스터·믹스(멱등). 같은 slug 라 마스터본이 있으면 건너뛴다. Suno 호출 없음."""
    from services import music_master, music_mix, music_store

    slug = rec["slug"]
    briefs = [t for t in (rec.get("tracks") or []) if t.get("audio_id")]
    if not briefs:
        raise RuntimeError("복구할 곡이 없습니다(체크포인트에 트랙 없음).")
    try:
        rows = music_store.get_tracks_by_ids([t["audio_id"] for t in briefs], channel=rec.get("channel"))
        rows = [r for r in rows if r.get("r2_key") and r.get("audio_id")]
    except Exception:  # noqa: BLE001
        rows = []
    if not rows:
        rows = [t for t in briefs if t.get("r2_key")]  # DB 조회 실패 → 체크포인트 요약으로
    order = {t["audio_id"]: i for i, t in enumerate(briefs)}
    rows.sort(key=lambda r: order.get(r.get("audio_id"), 999))
    if not music_master.master_theme(slug, rows):
        raise RuntimeError("마스터링 실패(원본 음원 없음).")
    lyrics = _load_lyrics(slug, [r["audio_id"] for r in rows])
    mix = music_mix.build_mix(slug, rows, minutes=float(rec.get("minutes") or 10.0), lyrics_by_id=lyrics or None)
    if not mix or not mix.get("mp3_url"):
        raise RuntimeError("믹스 생성 실패.")
    return mix


def render_once(rec: dict, *, bg_path: str | None = None) -> dict:
    """체크포인트 rec 로 영상 1회 — 같은 mix 가 있으면 재사용(같은 mix_id → 큐 행 덮어씀)."""
    from services import music_video, music_viz_analyzer

    theme = dict(rec.get("theme") or {"slug": rec["slug"]})
    theme.setdefault("slug", rec["slug"])
    if rec.get("channel") and not theme.get("channel"):
        theme["channel"] = rec["channel"]
    mix = _load_mix(rec["slug"], rec["mix_id"]) if rec.get("mix_id") else None
    if not mix:
        mix = rebuild_mix(rec)
    viz_spec = music_viz_analyzer.analyze_song(theme, mix)
    if bg_path and os.path.exists(bg_path):
        return music_video.make_video(theme, mix, viz_spec=viz_spec, persist=True, background_path=bg_path)
    return music_video.make_video(theme, mix, viz_spec=viz_spec, persist=True)


def mark_failed_row(video: dict | None, reason: str) -> None:
    mix_id = (video or {}).get("video_id")
    if not mix_id:
        return
    from services import music_uploads
    music_uploads.mark_render_failed(
        mix_id, reason, clear_mp4=not str((video or {}).get("video_url") or "").startswith("http"),
    )


def recover_video(
    rec: dict, *, job_id: str, first_error: Exception, bg_path: str | None = None, step=None,
    attempts: int = RETRY_ATTEMPTS, wait: float | None = None, sleep=None,
) -> tuple[dict, dict]:
    """C — 영상 단계만 다시(같은 곡·주제·가사). 성공 시 (video, check). 최종 실패는 RuntimeError."""
    jobs = _jobs()
    wait = RETRY_WAIT_SEC if wait is None else wait
    sleep = sleep or time.sleep
    reason = getattr(first_error, "reason", None) or str(first_error)[:200]
    first_video = getattr(first_error, "video", None)
    if first_video and first_video.get("video_id"):
        rec = {**rec, "mix_id": first_video["video_id"]}
        mark_failed_row(first_video, reason)
    jobs.merge_metadata(job_id, {_RECOVERY_KEY: {**rec, "stage": "recovering", "last_error": reason}})
    for i in range(1, attempts + 1):
        label = f"복구 중 {i}/{attempts}"
        logger.warning("[recovery] %s job=%s 직전 실패=%s", label, job_id, reason)
        if step:
            step(label)
        jobs.merge_metadata(job_id, {"recovery_status": label, "recovery_reason": reason})
        if wait:
            sleep(wait)
        video = None
        try:
            video = render_once(rec, bg_path=bg_path)
            chk = check_render(video, channel=rec.get("channel"))
            if chk["ok"]:
                jobs.merge_metadata(job_id, {"recovery_status": f"복구 성공({i}/{attempts})", "render_check": chk})
                return video, chk
            reason = chk["reason"]
        except Exception as e:  # noqa: BLE001
            reason = str(e)[:200]
        if video and video.get("video_id"):
            rec = {**rec, "mix_id": video["video_id"]}
            mark_failed_row(video, reason)
    jobs.merge_metadata(job_id, {"recovery_status": f"복구 실패({reason})"[:200]})
    raise RuntimeError(f"렌더 실패 — 복구 {attempts}회 실패: {reason}")


# ── F 곡 재취득 ───────────────────────────────────────────────────────
def reacquire(item: dict, *, timeout: int = 60, interval: int = 5) -> list[dict]:
    """pending_store 1건 → record-info 로 트랙을 다시 받아 R2·DB 저장. 저장된 record 반환."""
    from services import music_suno
    tracks = music_suno.poll_task(item["task_id"], timeout=timeout, interval=interval)
    return music_suno.store_with_retry(
        item.get("slug") or "untitled", item["task_id"], tracks,
        genre=item.get("genre") or "", action=item.get("action") or "", channel=item.get("channel"),
    )


def reacquire_pending_stores(limit: int = 50) -> int:
    """최근 작업 metadata 의 pending_store 를 재취득 — 서버 시작·작업 시작 때 호출. 성공 건수."""
    jobs = _jobs()
    done = 0
    for row in jobs.list_recent_with_metadata(limit=limit):
        rec = (row.get("metadata") or {}).get(_RECOVERY_KEY) or {}
        pend = list(rec.get("pending_store") or [])
        if not pend:
            continue
        left, got = [], []
        for item in pend:
            try:
                recs = reacquire(item)
                got.extend({k: r.get(k) for k in ("audio_id", "r2_key", "duration", "title", "tags")} for r in recs[:1])
                done += 1
                logger.warning("[recovery] 곡 재취득 성공 taskId=%s job=%s", item.get("task_id"), row.get("job_id"))
            except Exception as e:  # noqa: BLE001
                left.append(item)
                logger.warning("[recovery] 곡 재취득 실패 taskId=%s: %s", item.get("task_id"), str(e)[:160])
        tracks = list(rec.get("tracks") or [])
        have = {t.get("audio_id") for t in tracks}
        tracks += [g for g in got if g.get("audio_id") not in have]
        jobs.merge_metadata(row["job_id"], {_RECOVERY_KEY: {**rec, "pending_store": left, "tracks": tracks}})
    return done


# ── E 재시작 복구 ─────────────────────────────────────────────────────
_RECOVERING = threading.Lock()


def is_stale(row: dict, now: datetime | None = None) -> bool:
    """끊긴 작업 판정 = updated_at 10분 경과 + 이 서버 시작 시각 이전."""
    try:
        ts = datetime.fromisoformat(str(row.get("updated_at")).replace("Z", "+00:00"))
    except ValueError:
        return False
    now = now or datetime.now(timezone.utc)
    return ts < now - timedelta(minutes=STALE_MIN) and ts < _STARTED_AT


def recover_stale_jobs(now: datetime | None = None, *, run_async: bool = True) -> list[str]:
    """scheduler 1분 tick 에서 호출. 끊긴 작업 1개씩 재개(곡 있음) 또는 failed 정리(곡 없음)."""
    from services import music_library, music_manual
    jobs = _jobs()
    handled: list[str] = []
    for row in jobs.list_unfinished():
        if row.get("type") == "auto_run" or not is_stale(row, now):
            continue
        jid = row["job_id"]
        rec = (row.get("metadata") or {}).get(_RECOVERY_KEY) or {}
        if not (rec.get("tracks") or rec.get("pending_store")):
            if jobs.reclaim_job(jid, row.get("updated_at")):
                jobs.fail_job(jid, "서버 재시작으로 중단(복구할 곡 없음)")
                logger.warning("[recovery] 끊긴 작업 정리(곡 없음) job=%s", jid)
                handled.append(jid)
            continue
        # 곡이 있는 작업 — 동시 1개. 수동·라이브러리 생성이 돌고 있으면 다음 tick.
        if _busy(music_manual) or _busy(music_library) or not _RECOVERING.acquire(blocking=False):
            continue
        if not jobs.reclaim_job(jid, row.get("updated_at")):
            _RECOVERING.release()
            continue
        handled.append(jid)
        if run_async:
            threading.Thread(target=_resume_safe, args=(jid, rec), name=f"recover-{jid[:8]}", daemon=True).start()
        else:
            _resume_safe(jid, rec)
        break  # 1개씩
    return handled


def _busy(mod) -> bool:
    aj = getattr(mod, "_active_job", None)
    return bool(aj and (getattr(mod, "_JOBS", {}).get(aj) or {}).get("status") == "running")


def _resume_safe(job_id: str, rec: dict) -> None:
    from services import music_manual, music_uploads
    jobs = _jobs()
    # 수동 생성 락을 잡아 다른 생성(자동 회차 포함)이 동시에 돌지 않게 한다.
    with music_manual._LOCK:
        music_manual._JOBS[job_id] = {"job_id": job_id, "status": "running", "step": "복구", "error": None}
        music_manual._active_job = job_id
    try:
        with Heartbeat(job_id):
            jobs.update_job_step(job_id, "video")
            if rec.get("pending_store"):
                reacquire_pending_stores()
                rec = ((jobs.get_job(job_id) or {}).get("metadata") or {}).get(_RECOVERY_KEY) or rec
            if not rec.get("tracks"):
                raise RuntimeError("서버 재시작으로 중단(재취득된 곡 없음)")
            logger.warning("[recovery] 재시작 복구 시작 job=%s 곡=%d stage=%s", job_id,
                           len(rec.get("tracks") or []), rec.get("stage"))
            bg_path, img_dir = None, None
            if rec.get("auto_image"):  # 운동 채널 — 배경을 다시 만든다(실패면 검은 배경, 합격본 재사용 포함)
                from services import music_auto_image
                img_dir = tempfile.mkdtemp(prefix="recimg_")
                bg_path, review = music_auto_image.prepare_for_render(
                    job_id, ((rec.get("theme") or {}).get("tag_combo") or {}).get("action"), img_dir,
                    channel=rec.get("channel"), genre=rec.get("genre_id"),
                )
            try:
                video, chk = recover_video(rec, job_id=job_id, first_error=RuntimeError("서버 재시작으로 중단"),
                                           bg_path=bg_path, attempts=RETRY_ATTEMPTS, wait=0)
                if rec.get("channel"):
                    music_uploads.set_channel(video["video_id"], rec["channel"])
                if bg_path:
                    from services import music_auto_image
                    music_auto_image.attach_after_render(
                        rec["slug"], video["video_id"], bg_path, video, channel=rec.get("channel"),
                    )
            finally:
                if img_dir:
                    shutil.rmtree(img_dir, ignore_errors=True)
            jobs.merge_metadata(job_id, {"render_check": chk})
            jobs.complete_job(job_id, mix_id=video["video_id"])
            logger.warning("[recovery] 재시작 복구 완료 job=%s mix_id=%s", job_id, video["video_id"])
    except Exception as e:  # noqa: BLE001
        jobs.fail_job(job_id, f"복구 실패: {e}")
        logger.warning("[recovery] 재시작 복구 실패 job=%s: %s", job_id, e)
    finally:
        with music_manual._LOCK:
            if music_manual._active_job == job_id:
                music_manual._active_job = None
            music_manual._JOBS.pop(job_id, None)
        _RECOVERING.release()
