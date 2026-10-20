"""쇼츠 사람 캐스트 — 채널별 실사 캐릭터 시트(프론트 /shorts/cast)용 백엔드 서비스.

백곰 /cast(sayeon_cast, 동물 8캐스트)와 **분리된** 경로다. 백곰 코드·키는 건드리지 않는다.
- 채널 축이 있다: R2 키 cast/{channel}/{role}/{aspect}.png (캐릭터 전용 버킷, Lifecycle 없음).
- 확정 상태는 R2 JSON cast/{channel}/state.json (Supabase 테이블·SQL 불필요).

일관성 핵심은 백곰과 같다: **정면을 먼저 t2i 로 만들고**, 나머지는 그 정면을 레퍼런스로
Kontext 에 넣어 생성한다. 사람은 얼굴이 정체성의 전부라 정면을 **상반신 정면**(얼굴이 크게
보이는 컷)으로 만들어 레퍼런스 품질을 높인다.

⚠️ 실존 인물 닮음 금지 — 프롬프트에 실존 인물 이름·사진을 쓰지 않고 '오리지널 가상 인물'을
명시한다. 캐릭터 이름은 메타데이터에 쓰지 않으므로 바이블에도 표시용 라벨만 둔다.
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

# ── 공통 스타일 ──────────────────────────────────────────────────────────
_PHOTO_STYLE = (
    "Photorealistic photograph, natural skin texture with pores, realistic proportions, "
    "soft even studio lighting, 50mm lens, sharp focus on the face, true-to-life colors"
)
_NEUTRAL_BG = (
    "a plain soft uniform light-gray studio background, evenly lit, "
    "no gradient, no props"
)
_ORIGINAL = (
    "He is an ORIGINAL fictional person — not based on, and not resembling, any real "
    "celebrity, athlete, idol, actor or public figure, and not a live-action version of any "
    "anime, manga or game character"
)
_HANDS = "if hands are visible: natural relaxed hands with exactly five fingers each, natural joints"
_CLEAN = "No text, no letters, no logos, no brand marks on clothing, no watermark"

# ── 아스펙트 정의 ────────────────────────────────────────────────────────
# front 는 t2i(레퍼런스 소스). 나머지는 front 를 레퍼런스로 Kontext. (key, 라벨, 묘사, 비율)
_REF_ASPECTS: list[tuple[str, str, str, str]] = [
    ("threequarter", "반측면",
     "a waist-up three-quarter (3/4) view, head and body turned about 45 degrees, "
     "same plain fitted dark t-shirt, neutral calm expression", "9:16"),
    ("side", "측면",
     "a waist-up side profile view, head and body turned 90 degrees to the side, "
     "same plain fitted dark t-shirt, neutral calm expression", "9:16"),
    ("workout_full", "운동복 전신",
     "a full-body front view standing relaxed, wearing a plain fitted black athletic "
     "t-shirt, black training shorts and plain white training shoes, the whole body visible "
     "head to toe with margin", "9:16"),
    ("casual_full", "일상복 전신",
     "a full-body front view standing relaxed, wearing everyday casual clothes — a plain "
     "gray hoodie, dark jogger pants and plain white sneakers, the whole body visible head to "
     "toe with margin", "9:16"),
    ("selfie_bust", "셀카 버스트",
     "a smartphone selfie framing: head and shoulders, one arm extended toward the camera "
     "holding the phone (the phone itself is out of frame), slight high angle, relaxed "
     "natural half-smile, wearing the plain fitted black athletic t-shirt", "9:16"),
    ("expr_smile", "표정: 웃음",
     "a front-facing head-and-shoulders close-up with a genuine bright smile, eyes "
     "slightly crinkled", "1:1"),
    ("expr_determined", "표정: 결의",
     "a front-facing head-and-shoulders close-up with a determined focused expression — "
     "a steady gaze, lips pressed, slightly furrowed brows, like before a fight", "1:1"),
]
ASPECT_LABELS: dict[str, str] = {"front": "정면", **{k: lbl for k, lbl, _, _ in _REF_ASPECTS}}
ASPECT_KEYS: list[str] = ["front", *(k for k, _, _, _ in _REF_ASPECTS)]
ASPECT_TOTAL = len(ASPECT_KEYS)  # 8

# ── 채널별 사람 캐스트 바이블 ────────────────────────────────────────────
# label 은 화면 표시용(메타데이터·영상에 쓰지 않음). core 가 프롬프트의 인물 묘사.
HUMAN_CAST: dict[str, list[dict]] = {
    "workout_music": [
        {
            "role": "lead",
            "label": "주인공",
            "summary": "20대 초반 동아시아 남성 · 격투기 선수 분위기 · 탄탄하고 마른 근육 · 짧은 흑발",
            "core": (
                "an East Asian man in his early twenties with the look of an amateur "
                "mixed-martial-arts fighter; a lean, toned, athletic build with defined but not "
                "bulky muscles (natural, not a bodybuilder); short natural black hair, slightly "
                "messy; clean-shaven; an unpolished, natural, down-to-earth face without makeup; "
                "calm confident eyes"
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
    """정면(t2i) — 얼굴이 크게 보이는 상반신 정면. 이후 모든 아스펙트의 레퍼런스."""
    return (
        f"Waist-up FRONT portrait of ONE single man on {_NEUTRAL_BG}. Person: {core}. "
        f"{_ORIGINAL}. Facing the camera directly, neutral calm expression, wearing a plain "
        f"fitted dark t-shirt, shoulders square to the camera. {_HANDS}. "
        f"{_PHOTO_STYLE}. {_CLEAN}."
    )


def ref_prompt(core: str, desc: str, *, bust: bool = False) -> str:
    """레퍼런스(정면) 기반 — 같은 얼굴·헤어·체형 유지, 지시한 시점·의상·표정만 변경."""
    keep = "face, facial features, skin tone, hairstyle, hair color and body build"
    return (
        "Using the reference photo as the EXACT same person, photograph the SAME single man "
        f"in {desc}. Person: {core}. Keep the identical {keep} as the reference — change ONLY "
        f"what is described. {_ORIGINAL}. Background: {_NEUTRAL_BG}. "
        f"{'' if bust else _HANDS + '. '}{_PHOTO_STYLE}. {_CLEAN}."
    )


def _aspect_prompt(core: str, aspect: str) -> tuple[str, str]:
    """(prompt, aspect_ratio)."""
    if aspect == "front":
        return front_prompt(core), "9:16"
    for key, _, desc, ratio in _REF_ASPECTS:
        if key == aspect:
            return ref_prompt(core, desc, bust=key.startswith("expr_")), ratio
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
    """{role: {"status": draft|approved, "updated_at"}}. 없음/오류 → {}."""
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
    state[role] = {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}
    r2_storage._get_client().put_object(
        Bucket=r2_storage._character_bucket(), Key=_state_key(channel),
        Body=json.dumps(state, ensure_ascii=False).encode(), ContentType="application/json")
    return state[role]


# ── 조회 ─────────────────────────────────────────────────────────────────
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
            "role": e["role"], "label": e["label"], "summary": e["summary"],
            "aspects": aspects, "status": (state.get(e["role"]) or {}).get("status", "draft"),
        })
    return out


def reference_urls(channel: str, role: str, aspects: tuple[str, ...] = ("front", "threequarter")) -> list[str]:
    """영상 단계(2단계)가 읽을 레퍼런스 URL — 확정(approved)된 캐스트만. 없으면 []."""
    if (read_state(channel).get(role) or {}).get("status") != "approved":
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
    """정면(t2i) → 나머지 7장(Kontext, ref=정면). 아스펙트별 부분 성공 허용."""
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
            res = _gen(kontext, prompt, ratio, local, refs=[str(front_local)])
            _upload(local, channel, role, key, res.source_url)
            generated.append(key)
        except Exception as e:  # noqa: BLE001
            logger.warning("[shorts-cast] 아스펙트 생성 실패(%s/%s/%s): %s", channel, role, key, e)
            failed.append(key)
        tick()
    return {"generated": generated, "failed": failed}


def regenerate_aspect(channel: str, role: str, aspect: str, output_dir: str | None = None) -> dict:
    """1장만 재생성. front 면 경고(나머지는 옛 정면 기준), 그 외는 R2 정면을 레퍼런스로."""
    entry = _require(get_entry(channel, role), channel, role)
    prompt, ratio = _aspect_prompt(entry["core"], aspect)
    out_dir = Path(output_dir or f"output/shorts/cast/{channel}/{role}")
    out_dir.mkdir(parents=True, exist_ok=True)
    local = out_dir / f"{aspect}.png"
    if aspect == "front":
        t2i = get_image_adapter()
        if not t2i.is_available():
            raise RuntimeError("이미지 어댑터 미설정(WAVESPEED/OPENAI 키) — 정면을 생성할 수 없습니다.")
        url = _upload(local, channel, role, "front", _gen(t2i, prompt, ratio, local).source_url)
        warning = "정면을 다시 만들었어요. 나머지는 이전 정면 기준이라 얼굴이 어긋날 수 있어요 — 전체 다시 생성을 권장합니다."
    else:
        kontext = get_kontext_adapter()
        if not kontext.is_available():
            raise RuntimeError("WAVESPEED_API_KEY 미설정 — 레퍼런스 아스펙트를 생성할 수 없습니다.")
        if aspect_key(channel, role, "front") not in _list_objects(channel):
            raise RuntimeError("정면(front)이 없습니다 — 먼저 전체를 생성하세요.")
        ref = _aspect_url(channel, role, "front")
        url = _upload(local, channel, role, aspect, _gen(kontext, prompt, ratio, local, refs=[ref]).source_url)
        warning = None
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
