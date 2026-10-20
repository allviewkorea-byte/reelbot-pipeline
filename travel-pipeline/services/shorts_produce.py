"""쇼츠 1편 제작 — 대본 → 장면별 레퍼런스 영상(Kling O3) → 자막·운동 채널 음악 합성 → 비공개 업로드.

흐름(회차 1편):
1. series.json 의 회차 → 대본 생성(shorts_script, 금지어 검사)
2. 장면마다 등장 인물 → 라벨 기준 레퍼런스(shorts_refs) + 외형 텍스트 → Kling O3 Reference 클립
   - 아기가 나오는 장면이 정책으로 거부(RefBlocked)되면 **아기 없는 대본(엄마·아빠만)으로 1회 대체**
3. ffmpeg: 클립을 1080×1920·30fps 로 맞춰 이어 붙이고, 한국어 자막(ASS, 백곰 자막 스타일 재사용) +
   운동 채널 곡(음악만, 목소리 없음)
4. 완성본을 R2 미리보기(shorts/{channel}/previews/)에 저장 → 릴봇 시즌 화면에서 재생
   upload=True 일 때만 운동 채널에 **비공개** 업로드(containsSyntheticMedia=True). 테스트 기본은 업로드 안 함.
5. series.json 에 대본·비용(영상 초×단가 실측)·video_id·요약 기록

음악 제작과 겹치지 않게 쇼츠 전용 락을 쓰고, 음악 수동/복구 작업이 돌고 있으면 시작하지 않는다.
공개 업로드는 하지 않는다(privacy 는 항상 private).
"""

from __future__ import annotations

import asyncio
import logging
import random
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from adapters.video import wavespeed_ref_video_adapter as rv
from services import shorts_refs, shorts_script, shorts_series

logger = logging.getLogger(__name__)

CHANNEL = "workout_music"
W, H, FPS = 1080, 1920, 30
HOOK_SEC = 2.0
AI_DISCLOSURE = (
    "🤖 이 영상의 가족과 장면은 AI로 생성한 가상 인물·장면입니다. "
    "💿 음악은 AI 음원 생성 시스템으로 제작한 창작 사운드입니다."
)
SHORTS_TAGS = ["쇼츠", "홈트", "운동", "돌잔치", "엄마운동", "육아", "가족", "챌린지", "workout", "shorts"]
_CAMERA = ("Vertical 9:16 frame. Camera: full-body or above-the-knee medium shot, steady, natural light. "
           "Photorealistic, natural hands with five fingers, no text, no logos, no watermark, "
           "no extra people. Tasteful family content; no close-ups of chest, hips or body parts.")

_LOCK = threading.Lock()
_RUN: dict = {"status": "idle"}


class Busy(RuntimeError):
    pass


def music_busy() -> bool:
    """음악 수동 제작·복구가 돌고 있으면 True(Railway 단일 워커 — ffmpeg 를 겹치지 않는다)."""
    try:
        from services import music_manual
        return getattr(music_manual, "_active_job", None) is not None
    except Exception:  # noqa: BLE001
        return False


def scene_prompt(scene: dict, bible: str, ep: dict) -> str:
    finale = " It is the baby's first-birthday party (dol-janchi); festive outfits." if ep.get("finale") else ""
    return f"{scene['action_en'].strip()} Characters: {bible}.{finale} Setting: {scene.get('place', '')}. {_CAMERA}"


# ── 영상 생성 ────────────────────────────────────────────────────────────
def _gen_clips(script: dict, ep: dict, *, adapter, channel: str) -> list[dict]:
    """장면별 클립. RefBlocked 는 그대로 올린다(호출부가 아기 대체 분기)."""
    clips = []
    for i, sc in enumerate(script["scenes"]):
        refs = shorts_refs.select(channel, sc["characters"], mom_stage=ep["mom_stage"],
                                  fmt=ep["format"], finale=bool(ep.get("finale")))
        prompt = scene_prompt(sc, refs["bible"], ep)
        try:
            res = asyncio.run(adapter.generate(prompt, refs["images"], sc["seconds"]))
        except rv.RefBlocked as e:
            e.scene = sc  # type: ignore[attr-defined]
            raise
        clips.append({"scene": i, "url": res.url, "seconds": res.seconds, "cost_usd": res.cost_usd,
                      "refs": refs["images"], "model": res.model, "task_id": res.task_id})
        logger.warning("[shorts] Day %s 장면 %d 생성 %ss $%.3f refs=%d", ep["day"], i + 1,
                       res.seconds, res.cost_usd, len(refs["images"]))
    return clips


def make_clips(series: dict, ep: dict, *, adapter=None, channel: str = CHANNEL,
               gen_script=shorts_script.generate) -> tuple[dict, list[dict], dict]:
    """(script, clips, notes). 아기 장면이 거부되면 아기 없는 대본으로 1회 대체."""
    adapter = adapter or rv.kling()
    notes: dict = {"baby_dropped": False, "blocked": None, "spent_usd": 0.0}
    script = gen_script(series, ep)
    try:
        return script, _gen_clips(script, ep, adapter=adapter, channel=channel), notes
    except rv.RefBlocked as e:
        scene = getattr(e, "scene", {}) or {}
        notes["blocked"] = str(e)[:300]
        if "baby" not in (scene.get("characters") or []):
            raise
        logger.warning("[shorts] Day %s 아기 레퍼런스 거부 → 아기 없는 대본으로 대체: %s", ep["day"], e)
        notes["baby_dropped"] = True
        script = gen_script(series, ep, exclude=("baby",))
        return script, _gen_clips(script, ep, adapter=adapter, channel=channel), notes


def seedance_probe(ep: dict, script: dict, *, channel: str = CHANNEL, adapter=None) -> dict:
    """Seedance 비교 1회 — 첫 장면을 5초로 요청해 레퍼런스가 거부되는지만 본다(결과 영상은 쓰지 않음)."""
    adapter = adapter or rv.seedance()
    sc = script["scenes"][0]
    refs = shorts_refs.select(channel, sc["characters"], mom_stage=ep["mom_stage"], fmt=ep["format"])
    out = {"model": adapter.model_id, "day": ep["day"], "roles": sc["characters"], "refs": len(refs["images"])}
    try:
        res = asyncio.run(adapter.generate(scene_prompt(sc, refs["bible"], ep), refs["images"], 5))
        out.update(accepted=True, url=res.url, cost_usd=res.cost_usd or None)
    except rv.RefBlocked as e:
        out.update(accepted=False, blocked=True, error=str(e)[:500])
    except Exception as e:  # noqa: BLE001 - 경로·필드 미확인 등 → 원문 기록
        out.update(accepted=False, blocked=False, error=str(e)[:500])
    return out


# ── 합성 ─────────────────────────────────────────────────────────────────
def _ff(args: list[str], cwd: Path) -> None:
    res = subprocess.run(["ffmpeg", "-y", "-v", "error", *args], cwd=str(cwd), capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg 실패: {res.stderr[-800:]}")


def subtitle_items(script: dict, total: float) -> list[dict]:
    """훅(0~2초) → 본 자막을 남은 시간에 고르게. 백곰 _build_ass 입력 형식."""
    items = [{"start": 0.0, "end": min(HOOK_SEC, total), "subtitle": script["hook"], "highlight": ""}]
    caps = [c for c in script.get("captions") or [] if c.strip()]
    if caps and total > HOOK_SEC:
        span = (total - HOOK_SEC) / len(caps)
        for i, c in enumerate(caps):
            items.append({"start": HOOK_SEC + i * span, "end": HOOK_SEC + (i + 1) * span - 0.05,
                          "subtitle": c, "highlight": ""})
    return items


def assemble(clip_paths: list[Path], script: dict, music: Path | None, out: Path, cwd: Path) -> float:
    """클립 정규화·연결 + 자막 번인 + 음악(없으면 무음). 반환: 길이(초)."""
    from services.sayeon_assemble import _build_ass
    norm = []
    for i, p in enumerate(clip_paths):
        n = cwd / f"n{i}.mp4"
        _ff(["-i", p.name, "-an", "-vf",
             f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", n.name], cwd)
        norm.append(n)
    (cwd / "list.txt").write_text("".join(f"file '{n.name}'\n" for n in norm))
    _ff(["-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", "joined.mp4"], cwd)
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", "joined.mp4"],
        cwd=str(cwd), capture_output=True, text=True).stdout.strip() or 0)
    _build_ass(subtitle_items(script, dur), cwd / "subs.ass")
    if music is not None:
        audio = ["-stream_loop", "-1", "-i", music.name]
        af = (f"[1:a]atrim=0:{dur:.2f},afade=t=in:d=0.4,afade=t=out:st={max(0.0, dur - 1.2):.2f}:d=1.2,"
              "loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    else:
        audio = ["-f", "lavfi", "-t", f"{dur:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
        af = "[1:a]anull[a]"
    _ff(["-i", "joined.mp4", *audio, "-filter_complex", f"[0:v]ass=subs.ass[v];{af}",
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-t", f"{dur:.2f}",
         "-movflags", "+faststart", out.name], cwd)
    return dur


def pick_music(channel: str = CHANNEL) -> dict | None:
    """운동 채널 적립곡 1곡(랜덤). 없으면 None(무음 합성)."""
    from adapters import r2_storage
    from services import music_store
    rows = [r for r in music_store.list_library(channel=channel, limit=100)
            if r.get("r2_key") and r.get("status") == "SUCCESS"]
    if not rows:
        return None
    r = random.choice(rows)
    return {"audio_id": r.get("audio_id"), "title": r.get("title"), "url": r2_storage.music_object_url(r["r2_key"])}


# ── 업로드 ───────────────────────────────────────────────────────────────
def build_metadata(ep: dict, script: dict) -> tuple[str, str, list[str]]:
    title = f"{script['hook']} | 돌잔치 {ep['dday']} 엄마 챌린지 Day {ep['day']} #Shorts"[:100]
    desc = "\n".join([
        f"돌잔치 {ep['dday']}, 엄마의 2주 챌린지 — Day {ep['day']}",
        script.get("summary") or "",
        "",
        AI_DISCLOSURE,
        "",
        "#Shorts #홈트 #돌잔치 #엄마운동 #육아",
    ])
    return title, desc, list(SHORTS_TAGS)


def upload_private(mp4: Path, ep: dict, script: dict, channel: str = CHANNEL) -> dict:
    """운동 채널 비공개 업로드 + (env PLAYLIST_WORKOUT_SHORTS) 재생목록. music_uploads 에는 기록하지 않음."""
    import os

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    from services.music_youtube_oauth import get_credentials
    from services.youtube_upload import _verify_music_channel, add_to_playlist

    title, desc, tags = build_metadata(ep, script)
    youtube = build("youtube", "v3", credentials=get_credentials(channel), cache_discovery=False)
    _verify_music_channel(youtube, channel)
    body = {
        "snippet": {"title": title, "description": desc, "tags": tags, "categoryId": "17",
                    "defaultLanguage": "ko", "defaultAudioLanguage": "ko"},
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": True},
    }
    media = MediaFileUpload(str(mp4), mimetype="video/mp4", chunksize=-1, resumable=True)
    vid = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()["id"]
    playlist = (os.getenv("PLAYLIST_WORKOUT_SHORTS") or "").strip()
    added = bool(playlist) and add_to_playlist(youtube, vid, playlist)
    logger.warning("[shorts] 비공개 업로드 video=%s playlist=%s", vid, playlist or "(미설정)")
    return {"video_id": vid, "video_url": f"https://www.youtube.com/watch?v={vid}", "playlist_added": added}


# ── 미리보기 저장 ────────────────────────────────────────────────────────
def preview_key(channel: str, day: int) -> str:
    return f"shorts/{channel}/previews/day{day:02d}-{int(time.time())}.mp4"


def save_preview(mp4: Path, channel: str, day: int) -> str:
    """완성본을 R2(캐릭터 버킷 — Lifecycle 없음)에 올리고 공개 URL 반환. 릴봇 화면에서 재생용."""
    from adapters import r2_storage
    return r2_storage.upload_image(
        str(mp4), preview_key(channel, day),
        bucket=r2_storage._character_bucket(),
        public_base_url=r2_storage._character_public_base(),
        content_type="video/mp4",
    )


# ── 1편 제작 ─────────────────────────────────────────────────────────────
def produce_episode(day: int, *, channel: str = CHANNEL, compare_seedance: bool = False,
                    upload: bool = False) -> dict:
    """Day N 1편 제작 → R2 미리보기 저장 → (upload=True 면) 비공개 업로드 → series.json 기록."""
    from services.sayeon_assemble import _fetch
    series = shorts_series.load(channel)
    ep = shorts_series.episode(series, day)
    t0 = time.time()
    shorts_series.update_episode(channel, day, status="producing")
    try:
        script, clips, notes = make_clips(series, ep, channel=channel)
        probe = seedance_probe(ep, script, channel=channel) if compare_seedance else None
        music = pick_music(channel)
        with tempfile.TemporaryDirectory(prefix="shorts_") as d:
            cwd = Path(d)
            paths = []
            for c in clips:
                p = cwd / f"c{c['scene']}.mp4"
                _fetch(c["url"], p)
                paths.append(p)
            mpath = None
            if music:
                mpath = cwd / "music.mp3"
                _fetch(music["url"], mpath)
            out = cwd / "short.mp4"
            dur = assemble(paths, script, mpath, out, cwd)
            preview_url = save_preview(out, channel, day)
            up = upload_private(out, ep, script, channel) if upload else {}
        video_usd = round(sum(c["cost_usd"] for c in clips), 3)
        cost = {"video_usd": video_usd, "video_seconds": sum(c["seconds"] for c in clips),
                "usd_per_sec": clips[0]["cost_usd"] / clips[0]["seconds"] if clips else None,
                "seedance_usd": (probe or {}).get("cost_usd"), "llm": "대본 1~3회(별도 집계: 대시보드 LLM 사용량)",
                "total_video_usd": round(video_usd + ((probe or {}).get("cost_usd") or 0), 3)}
        result = shorts_series.update_episode(
            channel, day, status="uploaded_private" if upload else "rendered",
            script=script, summary=script.get("summary"), cost=cost,
            video_id=up.get("video_id"), video_url=up.get("video_url"), preview_url=preview_url,
            duration_sec=round(dur, 1), music=music, clips=clips, notes=notes, seedance=probe,
            elapsed_sec=round(time.time() - t0))
        logger.warning("[shorts] Day %s 완료 — 영상 $%.2f, %ss, preview=%s, video=%s", day, video_usd,
                       round(dur), preview_url, up.get("video_id") or "(업로드 안 함)")
        return result
    except Exception as e:
        shorts_series.update_episode(channel, day, status="failed", error=str(e)[:500])
        raise


FAMILY_ROLES = ("dad", "mom", "mom_after", "baby", "family")


def unapproved_roles(channel: str = CHANNEL) -> list[str]:
    """시즌 1 에 필요한 5 role 중 현재 바이블 버전으로 확정되지 않은 것(state.json 기준)."""
    from services import shorts_cast
    state = shorts_cast.read_state(channel)
    return [r for r in FAMILY_ROLES if shorts_cast._status(state, r) != "approved"]


def run_test(days: list[int], *, channel: str = CHANNEL, compare_seedance: bool = True,
             upload: bool = False) -> None:
    """테스트 제작(BackgroundTasks) — Day 순서대로, Seedance 비교는 첫 편에서 1회만.
    upload=False(기본)면 유튜브에 올리지 않고 R2 미리보기만 남긴다."""
    if not _LOCK.acquire(blocking=False):
        raise Busy("쇼츠 제작이 이미 진행 중입니다.")
    try:
        _RUN.update(status="running", days=list(days), done=[], failed={}, started_at=time.time())
        for i, day in enumerate(days):
            _RUN["current"] = day
            if music_busy():
                _RUN["failed"][day] = "음악 제작 중 — 건너뜀"
                continue
            try:
                produce_episode(day, channel=channel, compare_seedance=compare_seedance and i == 0,
                                upload=upload)
                _RUN["done"].append(day)
            except Exception as e:  # noqa: BLE001 - 한 편 실패가 나머지를 막지 않음
                logger.warning("[shorts] Day %s 실패: %s", day, e)
                _RUN["failed"][day] = str(e)[:300]
        _RUN.update(status="done", current=None)
    finally:
        _LOCK.release()


def run_state() -> dict:
    return dict(_RUN)


def is_running() -> bool:
    return _LOCK.locked()
