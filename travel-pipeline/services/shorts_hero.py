"""쇼츠 hero — 형식 A '원테이크 괴력'(첫 테스트: 배트 3개 몸으로 부러뜨리기).

대표 결정(2026-10-21): 210cm 단독 주인공 hero · 자극적인 운동 동기부여 · **자막·글자·끝 카드 없음**,
목소리 없음 · 테스트는 유튜브 업로드 없이 릴봇 미리보기.

흐름(1편):
1. hero 확정 확인(#362 hero 캐스트, state.json approved) — 미확정이면 시작하지 않음
2. hero 레퍼런스(슬롯별 라벨: 상의 탈의면 face + turnaround_shirtless 정면·측면 + shirtless + scale) ≤7장
3. Kling O3 **Pro** reference 1클립(10초) — 리얼감 프롬프트(휴대폰 원본 촬영·CG 피부 금지·물리)
4. 프레임 격자 비전 검수(모핑·손가락·관절·CG 느낌·글자) → 불합격이면 재생성(최대 2회, 편당 상한 안에서)
5. 파열 순간 = 프레임 차분(scdet) 최대 → ElevenLabs 효과음(룸톤·배트 파열·짧은 숨/신음)을 그 프레임에
   맞춰 배치(신음 +0.45초), 작은 방 울림·살짝 거친 질감
6. 두 버전 미리보기: ① 음악 없음(효과음만 — 인스타용 겸) ② 후렴 쾅(파열 순간에 우리 곡 드롭이 들어옴)
7. 클립 보관함(R2 shorts/{ch}/clips/ + index.json) 저장, 실행 기록(R2 shorts/{ch}/hero_runs.json)
   — 관련 동영상 수동 연결용 '플리 영상 링크 + 곡 위치'까지 기록. SQL 없음.

편당 비용 상한: SHORTS_MAX_USD_PER_EPISODE(기본 $6) — 다음 생성 호출 전 누적+예상이 넘으면 멈춘다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from adapters import r2_storage

logger = logging.getLogger(__name__)

CHANNEL = "workout_music"
ROLE = "hero"
W, H, FPS = 1080, 1920, 30
MAX_REVIEW_RETRIES = 2


def cost_cap() -> float:
    try:
        return float(os.getenv("SHORTS_MAX_USD_PER_EPISODE", "6"))
    except ValueError:
        return 6.0


class HeroNotReady(RuntimeError):
    pass


class Busy(RuntimeError):
    pass


# ── 리얼감 규칙(대표 강조) ───────────────────────────────────────────────
REALISM = (
    "Raw, unedited smartphone footage, shot on a phone on a small tripod, as if a real person filmed it; "
    "natural indoor lighting as it is, no cinematic color grading, no glow, no HDR, no lens flares. "
    "Natural skin texture with real pores, sweat and slight visible veins; NOT glossy, NOT plastic, NOT CGI, "
    "NOT a 3D render. Realistic physics: objects bend and break gradually, splinters fly and fall with gravity, "
    "the mat compresses under the body, muscles contract with effort. No teleporting, no morphing, "
    "no objects passing through bodies, no extra limbs. Natural hands with five fingers. "
    "No text, no letters, no logos, no watermark, no other people."
)

# ── 형식 A 콘셉트 ───────────────────────────────────────────────────────
CONCEPTS: dict[str, dict] = {
    "bat_break": {
        "label": "배트 3개 몸으로 부러뜨리기",
        "outfit": "shirtless",
        "seconds": 10,
        "impact_window": (0.55, 0.98),
        "action": (
            "In a small dark studio with a plain white floor mat, the shirtless man sits on the mat holding "
            "a bundle of three plain unbranded wooden baseball bats. He wraps his legs around the bundle, "
            "grips it with both arms, then rolls onto his side and twists with his whole body, straining hard; "
            "the bats bend and then snap in the middle around the last quarter of the clip, with wood "
            "splinters bursting and falling onto the mat; he exhales hard. Camera: fixed front view at chest "
            "height for most of the shot, then a slight slow push-in from a low angle as the bats break, with "
            "a brief half-second slow motion on the splinters."
        ),
        "sfx": {
            "room": ("quiet small room tone, faint hum of a small indoor studio, close phone microphone, "
                     "subtle body movement on a gym mat", None),
            "impact": ("very close loud sharp crack of three wooden baseball bats snapping at once, wood "
                       "splitting and splinters scattering and falling on a rubber mat, small room, recorded "
                       "on a phone", 2.0),
            "breath": ("one short heavy male exhale and grunt after exertion, close to the microphone, "
                       "no words, small room", 1.2),
        },
        "breath_offset": 0.45,
        "note": "AI로 생성한 영상입니다. 따라 하지 마세요.",
    },
}

# ── 금지 규칙 검사(위험 행동 유도·로고·실존 곡/인물·선정·흡연음주·비하) ─────────
_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(nike|adidas|puma|under\s*armour|reebok|lululemon|red\s*bull|monster\s*energy|coca[\s-]*cola|"
                r"pepsi|gatorade|branded|brand\s+name)\b", re.I), "브랜드"),
    (re.compile(r"we\s*will\s*rock\s*you|queen\b|freddie|eye\s+of\s+the\s+tiger|rocky\s+theme|"
                r"till\s+i\s+collapse|eminem", re.I), "실존 곡·가수"),
    (re.compile(r"\b(cigarette|smok(e|ing)|vape|beer|soju|alcohol|whisk(e)?y|drunk)\b|담배|흡연|음주|술자리|술병|맥주|소주", re.I),
     "흡연·음주"),
    (re.compile(r"close[\s-]*up\s+(of\s+)?(the\s+|his\s+)?(chest|crotch|butt|buttocks|groin)|sexy|seductive|"
                r"nude|naked|underwear|thong", re.I), "선정적 구도"),
    (re.compile(r"try\s+(this|it)\s+at\s+home|따라\s*해\s*(보세요|봐)|집에서\s*해\s*보", re.I), "위험 행동 따라 하기 유도"),
    (re.compile(r"lift(s|ing)?\s+(a\s+)?(car|truck|bus)|lifting\s+a\s+vehicle|차를?\s*들", re.I), "위험 괴력 연출(차량)"),
    (re.compile(r"\b(fat|ugly|loser|weak\s+people)\b|뚱뚱|못생|돼지|약골|한심", re.I), "외모·체형 비하"),
]


def check_rules(*texts: str) -> list[str]:
    """콘텐츠(콘셉트 동작·설명란·제목) 위반 사유. 안전 문구(REALISM)는 검사 대상이 아니다."""
    blob = "\n".join(t for t in texts if t)
    found = []
    for pat, why in _RULES:
        m = pat.search(blob)
        if m:
            found.append(f"{why}: '{m.group(0)}'")
    return found


# ── hero 상태 · 레퍼런스 ─────────────────────────────────────────────────
def hero_status(channel: str = CHANNEL) -> dict:
    from services import shorts_cast as sc
    entry = sc.get_entry(channel, ROLE)
    if not entry:
        return {"ready": False, "reason": "hero 캐스트가 아직 없어요(#362 머지 필요)."}
    if sc._status(sc.read_state(channel), ROLE) != "approved":
        return {"ready": False, "reason": "hero 캐릭터 시트를 확정해 주세요(/shorts/cast)."}
    return {"ready": True, "reason": ""}


def slot_refs(channel: str = CHANNEL) -> dict[str, list[str]]:
    """hero 슬롯별 레퍼런스 — 단일 슬롯은 key, 시트는 '{slot}:{label}'(자르지 않기면 '{slot}:sheet').

    shorts_cast_upload.labeled_refs 는 라벨을 슬롯 구분 없이 합쳐(상의 탈의 정면과 운동복 정면이 섞임)
    의상별로 고를 수 없어서, 같은 메타(slots.json)·R2 목록을 슬롯 단위로 읽는다.
    """
    from services import shorts_cast as sc
    from services import shorts_cast_upload as up
    entry = sc.get_entry(channel, ROLE) or {}
    objects = sc._list_objects(channel)
    meta = up.read_meta(channel).get(ROLE) or {}
    out: dict[str, list[str]] = {}
    for slot in entry.get("slots", []):
        key = slot["key"]
        if sc.aspect_key(channel, ROLE, key) not in objects:
            continue
        if slot["kind"] == "single":
            out[key] = [sc._aspect_url(channel, ROLE, key)]
            continue
        m = meta.get(key) or {}
        if not m.get("crop", True):
            out[f"{key}:sheet"] = [sc._aspect_url(channel, ROLE, key)]
            continue
        for i, label in enumerate(m.get("labels") or []):
            name = f"{key}_p{i}"
            if label != "unused" and sc.aspect_key(channel, ROLE, name) in objects:
                out.setdefault(f"{key}:{label}", []).append(sc._aspect_url(channel, ROLE, name))
    return out


_OUTFIT_PLAN = {
    # 우선순위 순 — 앞에서부터 7장까지
    "shirtless": ["face", "turnaround_shirtless:front", "turnaround_shirtless:sheet", "shirtless",
                  "turnaround_shirtless:threequarter", "turnaround_shirtless:side", "scale",
                  "turnaround_shirtless:back"],
    "sportswear": ["face", "turnaround:front", "turnaround:sheet", "turnaround:threequarter",
                   "turnaround:side", "scale", "expressions:expr"],
    "casual": ["face", "casual", "turnaround:front", "scale", "expressions:expr"],
}


def select_refs(refs: dict[str, list[str]], outfit: str, limit: int = 7) -> list[str]:
    out: list[str] = []
    for k in _OUTFIT_PLAN[outfit]:
        for u in refs.get(k, [])[:1]:
            if u not in out and len(out) < limit:
                out.append(u)
    return out


def build_prompt(concept: dict, bible: str) -> str:
    return f"{concept['action']} The man: {bible}. {REALISM}"


# ── 검수 ─────────────────────────────────────────────────────────────────
REVIEW_SYSTEM = (
    "너는 AI 생성 쇼츠 영상의 품질 검수자다. 입력 이미지는 한 영상에서 뽑은 프레임 여러 장의 격자다"
    "(사용자 문구의 '배경 이미지'는 이 격자를 뜻한다). 아래 중 하나라도 보이면 불합격:\n"
    "1) 몸·얼굴이 프레임 사이에서 녹거나 바뀌는 모핑, 팔다리가 늘어나거나 개수가 틀림\n"
    "2) 손가락 개수·관절 방향 왜곡\n"
    "3) 번들거리는 CG/플라스틱 피부, 3D 렌더 느낌, 과한 영화 색보정·글로우\n"
    "4) 화면 속 글자·로고·워터마크·간판\n"
    "5) 물체가 몸을 관통하거나 순간이동, 물리적으로 불가능한 파손\n"
    "6) 선정적 구도(가슴·사타구니 클로즈업)\n"
    "애매하면 불합격. JSON 만 출력: {\"pass\": true|false, \"reasons\": [\"짧은 사유\", ...]}"
)


def review_clip(clip: Path, duration: float, workdir: Path) -> dict:
    from services import music_auto_image, music_recovery
    times = [round(duration * f, 2) for f in (0.08, 0.3, 0.5, 0.7, 0.85, 0.95)]
    sheet = music_recovery.build_contact_sheet(str(clip), times, str(workdir / "review.jpg"))
    return music_auto_image.review_image(sheet, system=REVIEW_SYSTEM)


# ── 사운드 디자인 · 합성 ─────────────────────────────────────────────────
def _ff(args: list[str], cwd: Path) -> None:
    res = subprocess.run(["ffmpeg", "-y", "-v", "error", *args], cwd=str(cwd), capture_output=True, text=True,
                         timeout=600)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg 실패: {res.stderr[-600:]}")


# 작은 방 울림 + 살짝 거친 질감(효과음이 영상보다 깨끗하면 안 됨).
_ROOM = "aecho=0.8:0.55:18|37:0.22|0.12"
_ROUGH = "highpass=f=70,lowpass=f=9500,acompressor=threshold=-18dB:ratio=3:attack=5:release=80"


def peak_normalize(src: Path, out: Path, cwd: Path, target_db: float = -1.0) -> float:
    """가장 큰 소리(파열음)가 target_db 가 되도록 고정 이득. 반환: 적용 이득(dB).

    loudnorm(평균 라우드니스 맞춤)은 앞부분의 조용한 룸톤까지 -14 LUFS 로 끌어올려 '무음 긴장'을
    없애므로 쓰지 않는다 — 조용한 구간은 조용하게, 파열음만 크게."""
    res = subprocess.run(["ffmpeg", "-v", "info", "-i", src.name, "-af", "volumedetect", "-f", "null", "-"],
                         cwd=str(cwd), capture_output=True, text=True, timeout=120)
    m = re.search(r"max_volume:\s*(-?[\d.]+) dB", res.stderr)
    gain = target_db - float(m.group(1)) if m else 0.0
    _ff(["-i", src.name, "-af", f"volume={gain:.2f}dB,alimiter=limit=0.95", "-ar", "44100", out.name], cwd)
    return round(gain, 2)


def mix_sfx(room: Path, impact: Path, breath: Path, duration: float, impact_t: float, breath_t: float,
            out: Path, cwd: Path) -> None:
    """룸톤(전체) + 파열음(impact_t) + 숨/신음(breath_t) → out(wav). 소리 위치는 지연(adelay)으로 정렬."""
    d_imp, d_br = int(round(impact_t * 1000)), int(round(breath_t * 1000))
    fc = (
        f"[0:a]aresample=44100,aformat=channel_layouts=stereo,atrim=0:{duration:.3f},volume=-26dB[r];"
        f"[1:a]aresample=44100,aformat=channel_layouts=stereo,{_ROOM},adelay={d_imp}|{d_imp}[i];"
        f"[2:a]aresample=44100,aformat=channel_layouts=stereo,{_ROOM},volume=-5dB,adelay={d_br}|{d_br}[b];"
        "anoisesrc=c=pink:a=0.002:r=44100,aformat=channel_layouts=stereo[n];"
        f"[r][i][b][n]amix=inputs=4:duration=first:normalize=0,{_ROUGH},atrim=0:{duration:.3f}[a]"
    )
    raw = cwd / f"_raw_{out.name}"
    _ff(["-stream_loop", "-1", "-i", room.name, "-i", impact.name, "-i", breath.name,
         "-filter_complex", fc, "-map", "[a]", "-ar", "44100", raw.name], cwd)
    peak_normalize(raw, out, cwd)


def mix_slam(sfx: Path, music: Path, music_drop: float, impact_t: float, duration: float,
             out: Path, cwd: Path) -> None:
    """효과음 + 우리 곡: 곡의 드롭 지점(music_drop)이 영상 파열 순간(impact_t)에 정확히 오도록 배치."""
    tail = max(0.3, duration - impact_t)
    d = int(round(impact_t * 1000))
    fc = (
        f"[1:a]atrim=start={music_drop:.3f}:duration={tail:.3f},asetpts=PTS-STARTPTS,"
        f"aresample=44100,aformat=channel_layouts=stereo,afade=t=out:st={max(0.0, tail - 0.4):.3f}:d=0.4,"
        f"volume=-4dB,adelay={d}|{d}[m];"
        f"[0:a][m]amix=inputs=2:duration=first:normalize=0,atrim=0:{duration:.3f}[a]"
    )
    raw = cwd / f"_raw_{out.name}"
    _ff(["-i", sfx.name, "-i", music.name, "-filter_complex", fc, "-map", "[a]", "-ar", "44100", raw.name], cwd)
    peak_normalize(raw, out, cwd)


def normalize_video(clip: Path, out: Path, cwd: Path) -> None:
    _ff(["-i", clip.name, "-an", "-vf",
         f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", out.name], cwd)


def mux(video: Path, audio: Path, out: Path, cwd: Path) -> None:
    """글자 없음 — 자막·끝 카드 없이 영상 + 오디오만."""
    _ff(["-i", video.name, "-i", audio.name, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out.name], cwd)


def audio_peak_time(path: Path, *, after: float = 0.0, before: float | None = None) -> float:
    """[after, before] 구간에서 에너지 상승이 가장 큰 시각(싱크 검증용).

    파열음 측정은 before=파열+0.3초로 잘라 0.45초 뒤 숨소리를 파열음으로 오인하지 않게 한다."""
    from services import shorts_audio
    r = shorts_audio.rms_curve(shorts_audio.decode(str(path)))
    on = shorts_audio.onset_curve(r)
    start = int(after * shorts_audio.FPS)
    end = len(on) if before is None else min(len(on), int(before * shorts_audio.FPS) + 1)
    i = max(range(start, end), key=lambda k: on[k])
    return i / shorts_audio.FPS


# ── R2 기록 ──────────────────────────────────────────────────────────────
def _runs_key(channel: str) -> str:
    return f"shorts/{channel}/hero_runs.json"


def _clips_index_key(channel: str) -> str:
    return f"shorts/{channel}/clips/index.json"


def _read_json(key: str, default):
    if not r2_storage.is_available():
        return default
    try:
        obj = r2_storage._get_client().get_object(Bucket=r2_storage._music_bucket(), Key=key)
        return json.loads(obj["Body"].read())
    except Exception:  # noqa: BLE001
        return default


def _write_json(key: str, data) -> None:
    r2_storage._get_client().put_object(Bucket=r2_storage._music_bucket(), Key=key,
                                        Body=json.dumps(data, ensure_ascii=False).encode(),
                                        ContentType="application/json")


def read_runs(channel: str = CHANNEL) -> list[dict]:
    data = _read_json(_runs_key(channel), [])
    return data if isinstance(data, list) else []


def save_run(channel: str, run: dict) -> None:
    runs = [r for r in read_runs(channel) if r.get("id") != run["id"]]
    _write_json(_runs_key(channel), [run, *runs][:50])


def _put_video(path: Path, key: str) -> str:
    return r2_storage.upload_image(str(path), key, bucket=r2_storage._character_bucket(),
                                   public_base_url=r2_storage._character_public_base(), content_type="video/mp4")


def store_clip(channel: str, clip: Path, tags: dict) -> dict:
    """클립 보관함 — 다음 편 재사용(2단계)을 위해 태그와 함께 저장."""
    cid = f"clip-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}"
    url = _put_video(clip, f"shorts/{channel}/clips/{cid}.mp4")
    item = {"id": cid, "url": url, "created_at": datetime.now(timezone.utc).isoformat(), "used_in": [], **tags}
    index = _read_json(_clips_index_key(channel), [])
    _write_json(_clips_index_key(channel), [item, *(index if isinstance(index, list) else [])][:500])
    return item


def description(run: dict) -> str:
    """설명란(업로드는 (B) 단계) — 첫 줄 플리 영상 링크 + 안전·AI 문구. 곡명·가수명 없음."""
    lines = []
    if run.get("related", {}).get("link"):
        lines.append(f"▶ 전체 운동 플리: {run['related']['link']}")
    lines += [run.get("note") or "AI로 생성한 영상입니다. 따라 하지 마세요.", "#Shorts #운동 #운동자극 #workout"]
    return "\n".join(lines)


# ── 1편 제작 ─────────────────────────────────────────────────────────────
def _pick_song(channel: str) -> dict | None:
    from services import shorts_songs
    used = {r.get("song", {}).get("audio_id") for r in read_runs(channel)[:10]}
    song = shorts_songs.pick_analyzed(channel, exclude=used)
    if song:
        return song
    for cand in shorts_songs.candidates(channel)[:3]:
        if cand["audio_id"] in used:
            continue
        try:
            return shorts_songs.analyze_song(cand)
        except Exception as e:  # noqa: BLE001
            logger.warning("[shorts-hero] 곡 분석 실패 %s: %s", cand.get("audio_id"), e)
    return None


def produce(concept_id: str = "bat_break", *, channel: str = CHANNEL, adapter=None, sfx_gen=None,
            reviewer=None, fetch=None, song=None, store=True) -> dict:
    """형식 A 1편 → 두 버전 미리보기(R2) + 클립 보관함 + 실행 기록. 반환: run dict."""
    from adapters.sfx import elevenlabs_sfx
    from adapters.video import wavespeed_ref_video_adapter as rv
    from services import shorts_audio
    from services import shorts_cast as sc
    from services.sayeon_assemble import _fetch

    concept = CONCEPTS[concept_id]
    st = hero_status(channel)
    if not st["ready"]:
        raise HeroNotReady(st["reason"])
    viol = check_rules(concept["action"], concept["note"])
    if viol:
        raise ValueError(f"콘셉트가 금지 규칙에 걸립니다: {viol}")
    adapter = adapter or rv.kling()                     # 형식 A = Pro
    sfx_gen = sfx_gen or elevenlabs_sfx.generate
    reviewer = reviewer or review_clip
    fetch = fetch or _fetch
    cap = cost_cap()
    run_id = f"heroA-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:4]}"
    run: dict = {"id": run_id, "format": "A", "concept": concept_id, "label": concept["label"],
                 "status": "producing", "created_at": datetime.now(timezone.utc).isoformat(),
                 "note": concept["note"], "cost": {"kling_usd": 0.0, "kling_seconds": 0, "attempts": 0,
                                                    "sfx_credits": 0, "cap_usd": cap}}
    refs = select_refs(slot_refs(channel), concept["outfit"])
    if not refs:
        raise HeroNotReady("hero 레퍼런스 이미지가 없어요.")
    bible = (sc.get_entry(channel, ROLE) or {}).get("bible", "")
    base_prompt = build_prompt(concept, bible)
    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="shorts_heroA_") as d:
        cwd = Path(d)
        clip, review, avoid = None, None, []
        sec = concept["seconds"]
        for attempt in range(1 + MAX_REVIEW_RETRIES):
            est = sec * adapter.usd_per_sec
            if run["cost"]["kling_usd"] + est > cap + 1e-9:
                run["cost"]["stopped_by_cap"] = True
                logger.warning("[shorts-hero] 비용 상한 $%.2f — 재생성 중단", cap)
                break
            prompt = base_prompt + (f" Avoid: {'; '.join(avoid)}." if avoid else "")
            res = asyncio.run(adapter.generate(prompt, refs, sec))
            run["cost"]["kling_usd"] = round(run["cost"]["kling_usd"] + res.cost_usd, 3)
            run["cost"]["kling_seconds"] += res.seconds
            run["cost"]["attempts"] = attempt + 1
            clip = cwd / f"raw{attempt}.mp4"
            fetch(res.url, clip)
            run["model"], run["prompt"], run["refs"] = res.model, prompt, refs
            try:
                review = reviewer(clip, shorts_audio.duration_of(str(clip)) or sec, cwd)
            except Exception as e:  # noqa: BLE001 - 검수 호출 실패는 통과로 보지 않되 진행
                review = {"pass": False, "reasons": [f"검수 실패: {str(e)[:120]}"], "error": True}
            if review.get("pass") or review.get("error"):
                break
            avoid = list(review.get("reasons") or [])[:4]
        if clip is None:
            raise RuntimeError("비용 상한 때문에 클립을 하나도 만들지 못했습니다.")
        run["review"] = review
        norm = cwd / "v.mp4"
        normalize_video(clip, norm, cwd)
        dur = shorts_audio.duration_of(str(norm))
        lo, hi = concept["impact_window"]
        impact = shorts_audio.impact_time(str(norm), dur, lo=lo, hi=hi)
        run["impact"] = impact
        files = {}
        for name, (text, length) in concept["sfx"].items():
            p = cwd / f"sfx_{name}.mp3"
            info = sfx_gen(text, length or dur, p)
            run["cost"]["sfx_credits"] += info.get("credits", 0)
            files[name] = p
        breath_t = min(dur - 0.2, impact["t"] + concept["breath_offset"])
        sfx_wav = cwd / "sfx.wav"
        mix_sfx(files["room"], files["impact"], files["breath"], dur, impact["t"], breath_t, sfx_wav, cwd)
        out_sfx = cwd / "short_sfx.mp4"
        mux(norm, sfx_wav, out_sfx, cwd)
        crack_at = audio_peak_time(sfx_wav, after=max(0.0, impact["t"] - 1.0), before=impact["t"] + 0.3)
        run["sync"] = {"impact_video": impact["t"], "crack_audio": round(crack_at, 3),
                       "crack_err_ms": round((crack_at - impact["t"]) * 1000), "breath_at": round(breath_t, 3)}
        song = song if song is not None else _pick_song(channel)
        out_slam = None
        if song:
            music = cwd / "song.mp3"
            fetch(song["audio_url"], music)
            slam_wav = cwd / "slam.wav"
            mix_slam(sfx_wav, music, float(song["drop"]), impact["t"], dur, slam_wav, cwd)
            out_slam = cwd / "short_slam.mp4"
            mux(norm, slam_wav, out_slam, cwd)
            run["song"] = {k: song.get(k) for k in ("audio_id", "title", "language", "bpm", "drop", "chorus_start",
                                                   "youtube_url", "start_in_video", "chorus_link", "chorus_mmss")}
            drop_pos = song["start_in_video"] + float(song["drop"])
            from services.shorts_songs import link_at, mmss
            run["related"] = {"youtube_url": song["youtube_url"], "link": link_at(song["youtube_url"], drop_pos),
                              "mmss": mmss(drop_pos)}
            run["sync"]["music_drop_at"] = round(impact["t"], 3)
        run["duration_sec"] = round(dur, 2)
        run["description"] = description(run)
        if store:
            base = f"shorts/{channel}/hero/{run_id}"
            run["previews"] = {"sfx": _put_video(out_sfx, f"{base}/sfx.mp4")}
            if out_slam:
                run["previews"]["slam"] = _put_video(out_slam, f"{base}/slam.mp4")
            item = store_clip(channel, clip, {
                "format": "A", "concept": concept_id, "place": "dark studio, white mat", "action": concept["label"],
                "outfit": concept["outfit"], "camera": "fixed front → low push-in, brief slow motion",
                "seconds": concept["seconds"], "model": run.get("model"), "cost_usd": run["cost"]["kling_usd"],
                "prompt": run.get("prompt"), "refs": refs, "review": review, "impact_sec": impact["t"]})
            run["clip_id"] = item["id"]
            item["used_in"].append(run_id)
        else:
            run["_local"] = {"sfx": str(out_sfx), "slam": str(out_slam) if out_slam else None}
            run["_files"] = {"sfx": out_sfx.read_bytes(), "slam": out_slam.read_bytes() if out_slam else None}
    run["status"] = "preview_ready"
    run["elapsed_sec"] = round(time.time() - t0)
    if store:
        save_run(channel, run)
    logger.warning("[shorts-hero] %s 완료 — Kling $%.2f(%d회), 효과음 %d크레딧, 파열 %.2fs(오차 %sms)",
                   run_id, run["cost"]["kling_usd"], run["cost"]["attempts"], run["cost"]["sfx_credits"],
                   impact["t"], run["sync"]["crack_err_ms"])
    return run


# ── 실행 상태(백그라운드) ────────────────────────────────────────────────
_LOCK = threading.Lock()
_STATE: dict = {"status": "idle"}


def is_running() -> bool:
    return _LOCK.locked()


def state() -> dict:
    return dict(_STATE)


def run_background(concept_id: str, channel: str = CHANNEL) -> None:
    if not _LOCK.acquire(blocking=False):
        raise Busy("hero 쇼츠 제작이 이미 진행 중입니다.")
    try:
        _STATE.update(status="running", concept=concept_id, started_at=time.time(), error=None)
        try:
            run = produce(concept_id, channel=channel)
            _STATE.update(status="done", run_id=run["id"])
        except Exception as e:  # noqa: BLE001
            logger.warning("[shorts-hero] 실패: %s", e)
            _STATE.update(status="failed", error=str(e)[:400])
            try:
                save_run(channel, {"id": f"heroA-fail-{int(time.time())}", "format": "A", "concept": concept_id,
                                   "status": "failed", "error": str(e)[:400],
                                   "created_at": datetime.now(timezone.utc).isoformat()})
            except Exception:  # noqa: BLE001
                pass
    finally:
        _LOCK.release()


# ── 쿵쿵따 스타디움 운동 앤섬(형식 A 타이어 샌드백 편용, 연주곡) ────────────
# 실존 곡 멜로디·가사·곡명 모방 금지 — 리듬 패턴(발 구르기·박수)만. Suno 1회 = 2클립, 둘 다 운동 채널
# 라이브러리(used=false)에 적립 → 플리 제작에도 쓸 수 있다(쇼츠 → 채널 유입 유지). 곡 개수 로직 무관.
ANTHEM_STYLE = (
    "Original stadium workout anthem, instrumental, about 80 BPM, heavy stomp-stomp-clap rhythm made of "
    "foot stomps and hand claps, huge booming drums, big arena reverb, a gritty distorted electric guitar riff "
    "entering in the second half, powerful and motivating, builds to a big final section, no vocals"
)
ANTHEM_NEGATIVE = "vocals, singing, lyrics, spoken words, choir words, EDM drop, trap hi-hats, cover song"
_ANTHEM: dict = {"status": "idle"}
_ANTHEM_LOCK = threading.Lock()


def anthem_theme(channel: str = CHANNEL) -> dict:
    return {"theme_slug": f"shorts-anthem-{datetime.now(timezone.utc):%Y%m%d%H%M%S}", "instrumental": True,
            "style": ANTHEM_STYLE, "title": "", "negativeTags": ANTHEM_NEGATIVE, "language": "inst",
            "action": "workout", "channel": channel}


def anthem_state() -> dict:
    return dict(_ANTHEM)


def make_anthem(channel: str = CHANNEL, *, generate=None) -> dict:
    """Suno 연주곡 1회(=2클립) 생성 → 운동 채널 라이브러리 적립."""
    from services import music_suno
    if not _ANTHEM_LOCK.acquire(blocking=False):
        raise Busy("앤섬 생성이 이미 진행 중입니다.")
    try:
        generate = generate or music_suno.generate_and_store
        theme = anthem_theme(channel)
        _ANTHEM.update(status="running", theme_slug=theme["theme_slug"], started_at=time.time(), error=None)
        try:
            res = generate(theme, channel=channel)
            tracks = [{"audio_id": t.get("audio_id"), "title": t.get("title"), "duration": t.get("duration")}
                      for t in res.get("tracks") or []]
            _ANTHEM.update(status="done", tracks=tracks)
            return {"theme_slug": theme["theme_slug"], "tracks": tracks}
        except Exception as e:  # noqa: BLE001
            _ANTHEM.update(status="failed", error=str(e)[:300])
            raise
    finally:
        _ANTHEM_LOCK.release()
