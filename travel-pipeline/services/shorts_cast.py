"""쇼츠 사람 캐스트 — 채널별 실사 캐릭터 시트(프론트 /shorts/cast)용 백엔드 서비스.

백곰 /cast(sayeon_cast, 동물 8캐스트)와 **분리된** 경로다. 백곰 코드·키는 건드리지 않는다.
- 채널 축이 있다: R2 키 cast/{channel}/{role}/{aspect}.png (캐릭터 전용 버킷, Lifecycle 없음).
- 확정 상태는 R2 JSON cast/{channel}/state.json (Supabase 테이블·SQL 불필요).

운동 채널 주인공은 **한 사람의 두 모드**다 — 평소 모드(부스스한 머리·뿔테·수염 자국)와
반전 모드(안경 벗고 머리 넘긴 깔끔한 모습). 얼굴(이목구비)이 같아야 하는 게 핵심이라:
- 평소 정면을 t2i 로 먼저 만들고(기준 얼굴), 평소 컷은 이 정면을 레퍼런스로 Kontext 생성.
- 반전 정면은 평소 정면에서 **헤어·안경·그루밍만** 바꿔 만들고, 나머지 반전 컷은 반전 정면을
  레퍼런스로 만든다(한 번에 바꾸는 양을 줄여 얼굴이 덜 흔들리게).

⚠️ 실존 인물 닮음 금지 — 프롬프트에 실존 인물 이름·사진을 쓰지 않고 '오리지널 가상 인물'을
명시한다. 캐릭터 이름(subtitle_name)은 **자막 전용**이며 프롬프트에 절대 넣지 않는다.
닮음 여부는 자동 판정하지 않는다(대표가 시트 확정 시 육안 승인).
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from adapters import (
    ImageGenerationRequest,
    get_image_adapter,
    get_kontext_adapter,
    r2_storage,
)

logger = logging.getLogger(__name__)

# 바이블이 바뀌면 올린다 — 이전 버전으로 확정한 시트는 자동으로 '검토 중'으로 돌아간다.
BIBLE_VERSION = 2

# ── 공통 스타일 ──────────────────────────────────────────────────────────
_PHOTO_STYLE = (
    "Photorealistic photograph, natural skin texture with pores, realistic proportions, "
    "soft even lighting, 50mm lens, sharp focus on the face, true-to-life colors"
)
_NEUTRAL_BG = (
    "a plain soft uniform light-gray studio background, evenly lit, "
    "no gradient, no props"
)
_GYM_BG = "a softly blurred modern gym interior in the background, soft natural gym lighting"
_ORIGINAL = (
    "He is an ORIGINAL fictional person — not based on, and not resembling, any real "
    "celebrity, athlete, idol, actor or public figure, and not a live-action version of any "
    "anime, manga or game character"
)
_HANDS = "if hands are visible: natural relaxed hands with exactly five fingers each, natural joints"
_CLEAN = "No text, no letters, no logos, no brand marks on clothing, no watermark"
_SAME_FACE = (
    "Keep the IDENTICAL face as the reference — same face shape, eyes, eyebrows, nose, lips, "
    "jawline, ears and skin tone; it must be clearly the same person"
)

# 모드별 외형(얼굴 묘사는 entry["core"], 여기는 헤어·안경·그루밍·체형만)
_DAILY_LOOK = (
    "everyday look: messy, unkempt shaggy black hair; black thick-rimmed glasses; light "
    "stubble from not shaving for a couple of days; a friendly, lazy, tired-but-cheerful "
    "office-slacker vibe — endearing, NOT dirty, NOT gross, NOT unpleasant"
)
_GLOW_LOOK = (
    "glow-up look: NO glasses; black hair neatly swept back off the forehead; clean-shaven "
    "and well-groomed; strikingly handsome like a fashion model or K-pop idol"
)
_GLOW_BODY = (
    "a slim athletic model-type physique — broad shoulders, clearly defined abs, lean muscles; "
    "NOT a bodybuilder, not bulky, not exaggerated"
)

# ── 아스펙트 정의 ────────────────────────────────────────────────────────
# (key, 라벨, 모드, 묘사, 레퍼런스로 쓸 아스펙트, 배경). front 는 t2i(기준 얼굴).
_REF_ASPECTS: list[tuple[str, str, str, str, str, str]] = [
    ("daily_threequarter", "평소 반측면", "daily",
     "a waist-up three-quarter (3/4) view, head and body turned about 45 degrees, wearing the "
     "same stretched-out faded t-shirt, the same glasses, hair and stubble",
     "front", _NEUTRAL_BG),
    ("daily_full", "평소 전신", "daily",
     "a full-body front view standing in a relaxed slouch, wearing a stretched-out faded "
     "t-shirt, loose sweatpants and plain slide slippers, the same glasses, hair and stubble, "
     "the whole body visible head to toe with margin",
     "front", _NEUTRAL_BG),
    ("office_full", "출근룩 전신", "daily",
     "a full-body front view of a morning commute look: a slightly wrinkled white dress shirt "
     "loosely tucked, dark slacks, plain dark shoes, a blue employee ID badge on a blue lanyard "
     "around the neck, the same glasses, hair and stubble, the whole body visible head to toe",
     "front", _NEUTRAL_BG),
    ("glow_front", "반전 정면", "glow",
     "a waist-up FRONT portrait after a glow-up: take off the glasses, sweep the hair neatly "
     "back off the forehead, shave cleanly; wearing a plain fitted black t-shirt. Change ONLY "
     "the hair, glasses and grooming",
     "front", _NEUTRAL_BG),
    ("glow_side", "반전 측면", "glow",
     "a waist-up side profile view, head and body turned 90 degrees to the side, the same "
     "swept-back hair, no glasses, clean-shaven, the same plain fitted black t-shirt",
     "glow_front", _NEUTRAL_BG),
    ("workout_full", "운동복 전신", "glow",
     "a full-body front view in a workout outfit: a plain gray hoodie, black training shorts "
     "and neon lime-green running shoes, standing ready to run, the same swept-back hair, no "
     "glasses, the whole body visible head to toe with margin",
     "glow_front", _NEUTRAL_BG),
    ("gym_shirtless", "체육관 상의 탈의 상반신", "glow",
     "a waist-up shot in a gym right after a workout, shirtless upper body with black gym "
     "shorts at the waist, natural confident standing pose, a light healthy sheen; a tasteful, "
     "NON-sexual athletic fitness context, the same swept-back hair, no glasses",
     "glow_front", _GYM_BG),
]
ASPECT_LABELS: dict[str, str] = {"front": "평소 정면 (기준 얼굴)", **{a[0]: a[1] for a in _REF_ASPECTS}}
ASPECT_KEYS: list[str] = ["front", *(a[0] for a in _REF_ASPECTS)]
ASPECT_TOTAL = len(ASPECT_KEYS)  # 8
_BY_KEY = {a[0]: a for a in _REF_ASPECTS}


def aspect_base(aspect: str) -> str | None:
    """이 아스펙트를 만들 때 레퍼런스로 쓰는 아스펙트(front 는 None)."""
    return _BY_KEY[aspect][4] if aspect in _BY_KEY else None


# ── 채널별 사람 캐스트 바이블 ────────────────────────────────────────────
# label·subtitle_name 은 화면·자막 전용 — 프롬프트(core)에는 이름이 들어가지 않는다.
HUMAN_CAST: dict[str, list[dict]] = {
    "workout_music": [
        {
            "role": "lead",
            "label": "주인공",
            "subtitle_name": "서준호",
            "summary": "25살 마케팅팀 사원 · 평소엔 친근한 폐인 → 운동할 땐 반전 존잘 · "
                       "시즌1: 2주 뒤 고등학교 동창회(D-14→D-day)",
            "core": (
                "a 25-year-old East Asian man who works as a junior office employee; a friendly, "
                "likable face with soft natural features, natural East Asian eyes, a straight nose, "
                "medium lips and a gentle jawline; slim, average height"
            ),
        },
    ],
}


def channels() -> list[str]:
    return list(HUMAN_CAST)


def get_entry(channel: str, role: str) -> dict | None:
    return next((e for e in HUMAN_CAST.get(channel, []) if e["role"] == role), None)


# ── 프롬프트 ─────────────────────────────────────────────────────────────
def front_prompt(core: str) -> str:
    """평소 정면(t2i) — 얼굴이 크게 보이는 상반신. 모든 아스펙트의 기준 얼굴."""
    return (
        f"Waist-up FRONT portrait of ONE single man on {_NEUTRAL_BG}. Person: {core}. "
        f"{_DAILY_LOOK}. Wearing a stretched-out faded plain t-shirt. {_ORIGINAL}. Facing "
        f"the camera directly, relaxed friendly expression, the face clearly visible. {_HANDS}. "
        f"{_PHOTO_STYLE}. {_CLEAN}."
    )


def ref_prompt(core: str, aspect: str) -> str:
    """레퍼런스 기반 — 같은 얼굴 유지, 지시한 시점·의상·모드만 변경."""
    _, _, mode, desc, base, bg = _BY_KEY[aspect]
    look = _DAILY_LOOK if mode == "daily" else f"{_GLOW_LOOK}. Body: {_GLOW_BODY}"
    ref = "reference photo" if base == "front" else "reference photo (the same man after his glow-up)"
    return (
        f"Using the {ref} as the EXACT same person, photograph the SAME single man in {desc}. "
        f"Person: {core}. {look}. {_SAME_FACE}. {_ORIGINAL}. Background: {bg}. {_HANDS}. "
        f"{_PHOTO_STYLE}. {_CLEAN}."
    )


def _aspect_prompt(core: str, aspect: str) -> tuple[str, str]:
    """(prompt, aspect_ratio). 모두 세로 9:16."""
    if aspect == "front":
        return front_prompt(core), "9:16"
    if aspect in _BY_KEY:
        return ref_prompt(core, aspect), "9:16"
    raise ValueError(f"알 수 없는 아스펙트입니다: {aspect}")


# ── R2 (캐릭터 전용 버킷) ────────────────────────────────────────────────
def aspect_key(channel: str, role: str, aspect: str) -> str:
    return f"cast/{channel}/{role}/{aspect}.png"


def _state_key(channel: str) -> str:
    return f"cast/{channel}/state.json"


def _aspect_url(channel: str, role: str, aspect: str) -> str:
    return f"{r2_storage._character_public_base()}/{aspect_key(channel, role, aspect)}"


def _list_objects(channel: str) -> dict[str, int]:
    """cast/{channel}/ 아래 {키: LastModified epoch}. 미설정/오류 → {}."""
    if not r2_storage.is_available():
        return {}
    out: dict[str, int] = {}
    try:
        client = r2_storage._get_client()
        pages = client.get_paginator("list_objects_v2").paginate(
            Bucket=r2_storage._character_bucket(), Prefix=f"cast/{channel}/")
        for page in pages:
            for obj in page.get("Contents", []):
                lm = obj.get("LastModified")
                out[obj["Key"]] = int(lm.timestamp()) if lm is not None else 0
    except Exception as e:  # noqa: BLE001
        logger.warning("[shorts-cast] R2 목록 조회 실패(%s): %s", channel, e)
    return out


def _upload(local: Path, channel: str, role: str, aspect: str, source_url: str | None) -> str:
    if r2_storage.is_available():
        try:
            return r2_storage.upload_image(
                str(local), aspect_key(channel, role, aspect),
                bucket=r2_storage._character_bucket(),
                public_base_url=r2_storage._character_public_base(),
                content_type="image/png",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[shorts-cast] R2 업로드 실패(%s/%s/%s): %s", channel, role, aspect, e)
    if source_url:
        logger.warning("[shorts-cast] %s/%s/%s 임시 CDN URL(R2 미저장)", channel, role, aspect)
        return source_url
    raise RuntimeError(f"아스펙트 {role}/{aspect} 저장 실패(R2 미설정·CDN 없음)")


def read_state(channel: str) -> dict:
    """{role: {"status": draft|approved, "version", "updated_at"}}. 없음/오류 → {}."""
    if not r2_storage.is_available():
        return {}
    try:
        obj = r2_storage._get_client().get_object(
            Bucket=r2_storage._character_bucket(), Key=_state_key(channel))
        data = json.loads(obj["Body"].read())
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 - 없음 → 빈 상태
        return {}


def set_status(channel: str, role: str, status: str) -> dict:
    if status not in ("draft", "approved"):
        raise ValueError(f"알 수 없는 상태입니다: {status}")
    if not r2_storage.is_available():
        raise RuntimeError("R2 미설정 — 확정 상태를 저장할 수 없습니다.")
    state = read_state(channel)
    state[role] = {"status": status, "version": BIBLE_VERSION,
                   "updated_at": datetime.now(timezone.utc).isoformat()}
    r2_storage._get_client().put_object(
        Bucket=r2_storage._character_bucket(), Key=_state_key(channel),
        Body=json.dumps(state, ensure_ascii=False).encode(), ContentType="application/json")
    return state[role]


# ── 조회 ─────────────────────────────────────────────────────────────────
def _status(state: dict, role: str) -> str:
    """확정은 현재 바이블 버전으로 확정한 것만 인정(바이블이 바뀌면 다시 승인)."""
    cur = state.get(role) or {}
    if cur.get("status") == "approved" and cur.get("version") == BIBLE_VERSION:
        return "approved"
    return "draft"


def list_cast(channel: str) -> list[dict]:
    """채널 캐스트 메타 + 아스펙트 URL(?v=LastModified) + 확정 상태."""
    objects = _list_objects(channel)
    state = read_state(channel)
    out = []
    for e in HUMAN_CAST.get(channel, []):
        aspects = {}
        for a in ASPECT_KEYS:
            k = aspect_key(channel, e["role"], a)
            if k in objects:
                aspects[a] = f"{_aspect_url(channel, e['role'], a)}?v={objects[k]}"
        out.append({
            "role": e["role"], "label": e["label"], "subtitle_name": e.get("subtitle_name"),
            "summary": e["summary"], "aspects": aspects, "status": _status(state, e["role"]),
        })
    return out


def reference_urls(channel: str, role: str, aspects: tuple[str, ...] = ("front", "glow_front")) -> list[str]:
    """영상 단계(2단계)가 읽을 레퍼런스 URL — 현재 바이블로 확정된 캐스트만. 없으면 [].

    기본 = 평소 정면 + 반전 정면(장면 모드에 맞춰 골라 쓴다)."""
    if _status(read_state(channel), role) != "approved":
        return []
    objects = _list_objects(channel)
    return [_aspect_url(channel, role, a) for a in aspects if aspect_key(channel, role, a) in objects]


# ── 생성 ─────────────────────────────────────────────────────────────────
def _require(entry: dict | None, channel: str, role: str) -> dict:
    if not entry:
        raise ValueError(f"알 수 없는 캐스트입니다: {channel}/{role}")
    return entry


def _gen(adapter, prompt: str, ratio: str, local: Path, refs: list[str] | None = None):
    req = ImageGenerationRequest(prompt=prompt, aspect_ratio=ratio, output_path=str(local),
                                 reference_images=refs,
                                 extra_params={"num_images": 1} if refs else None)
    return asyncio.run(adapter.generate(req))


def generate_all(channel: str, role: str, output_dir: str | None = None, on_progress=None) -> dict:
    """평소 정면(t2i) → 나머지 7장(Kontext, ref=aspect_base). 아스펙트별 부분 성공 허용.

    반전 정면이 실패하면 반전 컷들은 평소 정면을 레퍼런스로 대신 쓴다."""
    entry = _require(get_entry(channel, role), channel, role)
    t2i, kontext = get_image_adapter(), get_kontext_adapter()
    if not t2i.is_available():
        raise RuntimeError("이미지 어댑터 미설정(WAVESPEED/OPENAI 키) — 정면을 생성할 수 없습니다.")
    if not kontext.is_available():
        raise RuntimeError("WAVESPEED_API_KEY 미설정 — 레퍼런스 아스펙트를 생성할 수 없습니다.")
    out_dir = Path(output_dir or f"output/shorts/cast/{channel}/{role}")
    out_dir.mkdir(parents=True, exist_ok=True)
    generated: list[str] = []
    failed: list[str] = []

    def tick() -> None:
        if on_progress:
            try:
                on_progress(list(generated), list(failed))
            except Exception:  # noqa: BLE001
                pass

    front_local = out_dir / "front.png"
    prompt, ratio = _aspect_prompt(entry["core"], "front")
    try:
        res = _gen(t2i, prompt, ratio, front_local)
        _upload(front_local, channel, role, "front", res.source_url)
        generated.append("front")
    except Exception as e:  # noqa: BLE001
        logger.warning("[shorts-cast] 정면 생성 실패(%s/%s) — 나머지 건너뜀: %s", channel, role, e)
        failed = list(ASPECT_KEYS)
        tick()
        return {"generated": generated, "failed": failed}
    tick()
    for key in ASPECT_KEYS[1:]:
        prompt, ratio = _aspect_prompt(entry["core"], key)
        local = out_dir / f"{key}.png"
        try:
            base = out_dir / f"{aspect_base(key)}.png"
            if aspect_base(key) not in generated:
                base = front_local
            res = _gen(kontext, prompt, ratio, local, refs=[str(base)])
            _upload(local, channel, role, key, res.source_url)
            generated.append(key)
        except Exception as e:  # noqa: BLE001
            logger.warning("[shorts-cast] 아스펙트 생성 실패(%s/%s/%s): %s", channel, role, key, e)
            failed.append(key)
        tick()
    return {"generated": generated, "failed": failed}


def regenerate_aspect(channel: str, role: str, aspect: str, output_dir: str | None = None) -> dict:
    """1장만 재생성. 레퍼런스는 aspect_base(없으면 평소 정면). 기준 컷을 바꾸면 경고."""
    entry = _require(get_entry(channel, role), channel, role)
    prompt, ratio = _aspect_prompt(entry["core"], aspect)
    out_dir = Path(output_dir or f"output/shorts/cast/{channel}/{role}")
    out_dir.mkdir(parents=True, exist_ok=True)
    local = out_dir / f"{aspect}.png"
    dependents = [k for k in ASPECT_KEYS if aspect_base(k) == aspect]
    if aspect == "front":
        t2i = get_image_adapter()
        if not t2i.is_available():
            raise RuntimeError("이미지 어댑터 미설정(WAVESPEED/OPENAI 키) — 정면을 생성할 수 없습니다.")
        url = _upload(local, channel, role, "front", _gen(t2i, prompt, ratio, local).source_url)
        warning = "기준 얼굴(평소 정면)을 다시 만들었어요. 나머지 7장은 이전 얼굴 기준이라 어긋날 수 있어요 — 전체 다시 생성을 권장합니다."
    else:
        kontext = get_kontext_adapter()
        if not kontext.is_available():
            raise RuntimeError("WAVESPEED_API_KEY 미설정 — 레퍼런스 아스펙트를 생성할 수 없습니다.")
        objects = _list_objects(channel)
        if aspect_key(channel, role, "front") not in objects:
            raise RuntimeError("평소 정면(기준 얼굴)이 없습니다 — 먼저 전체를 생성하세요.")
        base = aspect_base(aspect) or "front"
        if aspect_key(channel, role, base) not in objects:
            base = "front"
        ref = _aspect_url(channel, role, base)
        url = _upload(local, channel, role, aspect, _gen(kontext, prompt, ratio, local, refs=[ref]).source_url)
        warning = None
        if dependents:
            names = ", ".join(ASPECT_LABELS[k] for k in dependents)
            warning = f"{ASPECT_LABELS[aspect]}을(를) 다시 만들었어요. {names}은(는) 이전 컷 기준이라 함께 다시 만드는 걸 권장합니다."
    _mark_draft(channel, role)
    out = {"role": role, "aspect": aspect, "url": f"{url}?v={int(time.time())}"}
    if warning:
        out["warning"] = warning
    return out


def _mark_draft(channel: str, role: str) -> None:
    """시트가 바뀌면 확정을 풀어 다시 승인받게 한다(실패해도 생성은 유효)."""
    try:
        set_status(channel, role, "draft")
    except Exception as e:  # noqa: BLE001
        logger.warning("[shorts-cast] 확정 해제 기록 실패(%s/%s): %s", channel, role, e)


# ── 비동기 진행상태(인메모리 — 재시작 시 소실, 이미지는 R2 에 남음) ─────────
_LOCK = threading.Lock()
_PROGRESS: dict[tuple[str, str], dict] = {}


def get_progress(channel: str, role: str) -> dict:
    with _LOCK:
        cur = _PROGRESS.get((channel, role)) or {"status": "idle", "generated": [], "failed": []}
        return {"channel": channel, "role": role, "status": cur["status"],
                "generated": list(cur["generated"]), "failed": list(cur["failed"]),
                "total": ASPECT_TOTAL}


def _set(channel: str, role: str, **kw) -> None:
    with _LOCK:
        cur = _PROGRESS.setdefault((channel, role), {"status": "idle", "generated": [], "failed": []})
        cur.update(kw)


def is_running(channel: str, role: str) -> bool:
    return get_progress(channel, role)["status"] == "running"


def run_generation(channel: str, role: str) -> None:
    """BackgroundTasks 진입점. 1장이라도 성공하면 done, 전무하면 failed."""
    _set(channel, role, status="running", generated=[], failed=[])
    _mark_draft(channel, role)
    try:
        res = generate_all(channel, role,
                           on_progress=lambda g, f: _set(channel, role, generated=g, failed=f))
        _set(channel, role, status="done" if res["generated"] else "failed", **res)
    except Exception as e:  # noqa: BLE001
        logger.warning("[shorts-cast] 생성 실패(%s/%s): %s", channel, role, e)
        _set(channel, role, status="failed")
