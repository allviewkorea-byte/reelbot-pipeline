"""쇼츠 사람 캐스트 — 채널별 실사 캐릭터 시트(프론트 /shorts/cast)용 백엔드 서비스.

백곰 /cast(sayeon_cast, 동물 8캐스트)와 **분리된** 경로다. 백곰 코드·키는 건드리지 않는다.
- 채널 축이 있다: R2 키 cast/{channel}/{role}/{aspect}.png (캐릭터 전용 버킷, Lifecycle 없음).
- 확정 상태는 R2 JSON cast/{channel}/state.json (Supabase 테이블·SQL 불필요).

운동 채널 주인공은 **한 사람의 두 모드**다 — 반전 모드(존잘·모델 비율)와 평소 모드(눌린 더벅머리·
두꺼운 뿔테·구부정한 백수). 얼굴(이목구비)이 같아야 하는 게 핵심이라:
- **반전 정면을 t2i 로 먼저 만들어 기준 얼굴(ANCHOR)로 삼고**, 나머지 7장은 모두 이 얼굴을
  레퍼런스로 Kontext 생성한다. 평소 컷은 같은 얼굴에 '망가뜨리기'(헤어·안경·그루밍·자세·옷)만 덧입힌다.
  (잘생긴 얼굴을 기준으로 두면 반전 컷이 '다른 사람·나이 든 증명사진'처럼 흐려지지 않는다.)

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
BIBLE_VERSION = 3

# ── 공통 스타일 ──────────────────────────────────────────────────────────
_PHOTO_STYLE = (
    "Photorealistic photograph, natural skin texture with pores, realistic proportions, "
    "50mm lens, sharp focus on the face, true-to-life colors"
)
_EDITORIAL = (
    "fashion-editorial magazine lighting with a soft key light and subtle rim light, "
    "a softly colored seamless studio backdrop in a muted warm-beige to dusty-teal tone"
)
_NEUTRAL_BG = (
    "a plain soft uniform light-gray studio background, evenly lit, "
    "no gradient, no props"
)
_GYM_BG = "a softly blurred modern gym interior in the background, moody editorial gym lighting"
_ORIGINAL = (
    "He is an ORIGINAL fictional person — not based on, and not resembling, any real "
    "celebrity, athlete, idol, actor or public figure, and not a live-action version of any "
    "anime, manga or game character"
)
_HANDS = "if hands are visible: natural relaxed hands with exactly five fingers each, natural joints"
_CLEAN = "No text, no letters, no logos, no brand marks on clothing or bags, no watermark"
_SAME_FACE = (
    "Keep the IDENTICAL face as the reference — same face shape, eyes, eyebrows, nose, lips, "
    "jawline, ears, skin tone and apparent age (mid-twenties); it must be clearly the same "
    "person — change ONLY the hair, glasses, grooming, posture and clothes described"
)
# 전신 비율(모델 8등신) — 머리가 크고 다리가 짧게 나오던 문제 대응
_PROPORTIONS = (
    "tall about 182 cm with model proportions — a small face, a long neck, broad shoulders, "
    "long legs, about eight heads tall (NOT a big head, NOT short legs); the ENTIRE body from "
    "the top of the head to the tips of the shoes in frame with margin; shot from a slightly "
    "low camera angle at waist height"
)

# 모드별 외형(얼굴 묘사는 entry["core"], 여기는 헤어·안경·그루밍·자세·체형만)
_GLOW_LOOK = (
    "glow-up look: no glasses; a stylish swept-back comma hairstyle (a soft comma-shaped curl "
    "at the front); clear, clean, well-groomed skin; clean-shaven; a confident, charismatic "
    "expression; strikingly handsome like a fashion model, youthful mid-twenties"
)
_GLOW_BODY = (
    "a slim athletic model-type physique — broad shoulders, clearly defined abs, lean muscles; "
    "NOT a bodybuilder, not bulky, not exaggerated"
)
_DAILY_LOOK = (
    "slacker everyday look of the same man: messy bedhead hair flattened on one side as if he "
    "just woke up, with bangs falling over the eyebrows; thick black-rimmed glasses that half "
    "hide his face; light stubble; faint dark circles; a slouched, hunched posture; a blank, "
    "expressionless face — an endearing, friendly do-nothing slacker, NOT dirty, NOT gross, "
    "NOT unpleasant, NOT sickly"
)

# ── 아스펙트 정의 ────────────────────────────────────────────────────────
ANCHOR = "glow_front"  # 기준 얼굴(t2i). 나머지는 모두 이 얼굴을 레퍼런스로.
# (key, 라벨, 모드, 묘사, 배경, 전신 여부)
_ASPECTS: list[tuple[str, str, str, str, str, bool]] = [
    ("glow_front", "반전 정면 (기준 얼굴)", "glow",
     "a waist-up FRONT portrait facing the camera, wearing a well-fitted plain black crew-neck "
     "t-shirt, shoulders square to the camera",
     _EDITORIAL, False),
    ("glow_side", "반전 측면", "glow",
     "a waist-up side profile view, head and body turned 90 degrees to the side, the same "
     "fitted black t-shirt, a confident relaxed pose",
     _EDITORIAL, False),
    ("gym_shirtless", "체육관 상의 탈의 상반신", "glow",
     "a waist-up shot in a gym right after a workout, shirtless upper body with black gym "
     "shorts at the waist, a natural confident standing pose, a light healthy sheen; a "
     "tasteful, NON-sexual athletic fitness context",
     _GYM_BG, False),
    ("workout_full", "운동복 전신", "glow",
     "a full-body front view in a workout outfit: a plain gray hoodie, black training shorts "
     "and neon lime-green running shoes, a confident ready-to-run stance",
     _EDITORIAL, True),
    ("glow_outing_full", "반전 외출 전신", "glow",
     "a full-body front view in a dressed-up everyday outfit for a class reunion: a well-fitted "
     "light knit sweater over a crisp shirt collar, tailored slacks and clean minimal leather "
     "sneakers, a confident easy pose",
     _EDITORIAL, True),
    ("daily_front", "평소 정면", "daily",
     "a waist-up FRONT view facing the camera, wearing a stretched-out faded plain t-shirt",
     _NEUTRAL_BG, False),
    ("daily_threequarter", "평소 반측면", "daily",
     "a waist-up three-quarter (3/4) view, head and body turned about 45 degrees, wearing the "
     "same stretched-out faded plain t-shirt",
     _NEUTRAL_BG, False),
    ("daily_full", "평소 전신", "daily",
     "a full-body front view wearing a stretched-out faded plain t-shirt, a baggy plain "
     "tracksuit with saggy stretched-out knees and plain slide slippers, holding a plain white "
     "convenience-store plastic bag",
     _NEUTRAL_BG, True),
]
_BY_KEY = {a[0]: a for a in _ASPECTS}
ASPECT_KEYS: list[str] = [a[0] for a in _ASPECTS]
ASPECT_LABELS: dict[str, str] = {a[0]: a[1] for a in _ASPECTS}
ASPECT_TOTAL = len(ASPECT_KEYS)  # 8


def aspect_base(aspect: str) -> str | None:
    """이 아스펙트를 만들 때 레퍼런스로 쓰는 아스펙트(기준 얼굴 자신은 None)."""
    return None if aspect == ANCHOR else ANCHOR


# ── 채널별 사람 캐스트 바이블 ────────────────────────────────────────────
# label·subtitle_name 은 화면·자막 전용 — 프롬프트(core)에는 이름이 들어가지 않는다.
# story 는 대본 단계(2단계)가 읽을 설정(프롬프트 이미지 생성에는 쓰지 않음).
# source: "generate"(이 모듈이 t2i·Kontext 로 시트 생성) | "upload"(대표가 외부 이미지를 업로드,
# 슬롯·자르기는 services/shorts_cast_upload). active=False 는 보관(코드·이미지 유지, 영상에 안 씀).
# 업로드 role 의 bible 은 영상 프롬프트에 이미지와 함께 넣는 외형 텍스트(영어).
HUMAN_CAST: dict[str, list[dict]] = {
    "workout_music": [
        {
            "role": "lead",
            "source": "generate",
            "active": False,  # 2026-10-20 대표 결정: 가족 3인으로 전환 — 서준호 시트는 보관
            "label": "주인공",
            "subtitle_name": "서준호",
            "summary": "26살 백수 · 원룸 자취 · 할 일이 없어 운동만 해서 몸이 좋음(반전의 이유) · "
                       "시즌1: 2주 뒤 동창회 D-14→D-day",
            "story": {
                "premise": "26살 백수, 원룸 자취. 할 일이 없어 운동만 해서 몸이 좋다.",
                "season1": "2주 뒤 고등학교 동창회 — 백수인 거 들키기 싫은데 첫사랑이 온대. D-14→D-day.",
                "formula": "평소 모드로 시작 → 반전 순간 → 반전 모드",
                "places": ["원룸", "편의점", "동네 공원", "체육관", "한강"],
            },
            "core": (
                "a 26-year-old East Asian man with a youthful mid-twenties face; a small, "
                "well-proportioned face with natural East Asian eyes, a straight nose, defined "
                "cheekbones and a clean jawline"
            ),
        },
        {
            "role": "dad", "source": "upload", "active": True, "label": "아빠",
            "summary": "30대 초반 · 근육질 헬스 마니아 · 코치 겸 방해꾼",
            "bible": (
                "the dad: a Korean man in his early thirties, muscular gym enthusiast; a black "
                "baseball cap worn backwards (no bangs showing), a black sleeveless tank top, white "
                "wristbands, gray joggers, black sneakers with white soles; no piercings"
            ),
            "slots": [
                {"key": "face", "label": "기준 얼굴", "kind": "single", "min": "face", "required": True},
                {"key": "expressions", "label": "표정 2×2", "kind": "grid"},
                {"key": "turnaround", "label": "전신 4방향", "kind": "strip", "cols": 4, "required": True},
                {"key": "action", "label": "헬스장 덤벨 컬", "kind": "single"},
            ],
        },
        {
            "role": "mom", "source": "upload", "active": True, "label": "엄마",
            "summary": "30대 초반 · 주근깨 · 시즌1 주인공(돌잔치 D-14 챌린지) · 변화 전",
            "bible": (
                "the mom: a Korean woman in her early thirties with freckles; a high ponytail with a "
                "thin black headband and a black scrunchie; a gray cropped sweatshirt hoodie (no "
                "zipper), light sky-blue leggings, white sneakers"
            ),
            "slots": [
                {"key": "face", "label": "기준 얼굴", "kind": "single", "min": "face", "required": True},
                {"key": "expressions", "label": "표정 2×2", "kind": "grid"},
                {"key": "turnaround", "label": "전신 4방향", "kind": "strip", "cols": 4, "required": True},
                {"key": "action_front", "label": "거실 스쿼트 정면", "kind": "single"},
                {"key": "action_side", "label": "거실 스쿼트 측면", "kind": "single"},
            ],
        },
        {
            "role": "mom_after", "source": "upload", "active": True, "label": "엄마 (변화 후)",
            "summary": "같은 얼굴·같은 옷 · 살짝 슬림·탄탄 · 밝고 자신감 있는 표정",
            "bible": (
                "the mom after two weeks of training: the SAME woman with the same face, freckles, "
                "hairstyle and the same outfit, now slightly slimmer and more toned, with a bright, "
                "confident expression"
            ),
            "slots": [
                {"key": "face", "label": "변화 후 얼굴", "kind": "single", "min": "face", "required": True},
                {"key": "fullbody", "label": "변화 후 전신", "kind": "single", "required": True},
            ],
        },
        {
            "role": "baby", "source": "upload", "active": True, "label": "아기",
            "summary": "돌 무렵 · 옆에서 따라 하는 귀여운 조연",
            "bible": (
                "the baby: a Korean baby about one year old with short black bob hair, wearing a plain "
                "pale-yellow short-sleeved romper and white socks"
            ),
            "slots": [
                {"key": "face", "label": "기준 얼굴", "kind": "single", "min": "face", "required": True},
                {"key": "expressions", "label": "표정 2×2", "kind": "grid"},
                {"key": "turnaround", "label": "전신 방향", "kind": "strip", "cols": 5, "required": True},
                {"key": "action", "label": "매트 위 스트레칭", "kind": "single"},
            ],
        },
        {
            "role": "family", "source": "upload", "active": True, "label": "가족 단체",
            "summary": "3인 단체 전신(키 비율 기준) · finale = 돌잔치 의상(선택)",
            "bible": "the family of three together: the dad, the mom and the baby",
            "slots": [
                {"key": "group", "label": "3인 단체 전신", "kind": "single", "required": True},
                {"key": "finale", "label": "돌잔치 의상 단체 (선택)", "kind": "single"},
            ],
        },
    ],
}


def channels() -> list[str]:
    return list(HUMAN_CAST)


def get_entry(channel: str, role: str) -> dict | None:
    return next((e for e in HUMAN_CAST.get(channel, []) if e["role"] == role), None)


def generated_entries(channel: str) -> list[dict]:
    """자동 생성(t2i·Kontext) role — 지금은 보관된 lead 뿐."""
    return [e for e in HUMAN_CAST.get(channel, []) if e.get("source", "generate") == "generate"]


# ── 프롬프트 ─────────────────────────────────────────────────────────────
def _look(mode: str) -> str:
    return f"{_GLOW_LOOK}. Body: {_GLOW_BODY}" if mode == "glow" else _DAILY_LOOK


def anchor_prompt(core: str) -> str:
    """반전 정면(t2i) — 기준 얼굴. 얼굴이 크게 보이는 상반신 화보 컷."""
    _, _, mode, desc, bg, _ = _BY_KEY[ANCHOR]
    return (
        f"A fashion-editorial photo of ONE single man: {desc}. Person: {core}. {_look(mode)}. "
        f"{_ORIGINAL}. Background and light: {bg}. {_HANDS}. {_PHOTO_STYLE}. {_CLEAN}."
    )


def ref_prompt(core: str, aspect: str) -> str:
    """기준 얼굴 레퍼런스 기반 — 같은 이목구비 유지, 헤어·안경·그루밍·자세·옷만 변경."""
    _, _, mode, desc, bg, full = _BY_KEY[aspect]
    body = f" Body proportions: {_PROPORTIONS}." if full else ""
    return (
        "Using the reference photo as the EXACT same person, photograph the SAME single man in "
        f"{desc}. Person: {core}. {_look(mode)}.{body} {_SAME_FACE}. {_ORIGINAL}. "
        f"Background and light: {bg}. {_HANDS}. {_PHOTO_STYLE}. {_CLEAN}."
    )


def _aspect_prompt(core: str, aspect: str) -> tuple[str, str]:
    """(prompt, aspect_ratio). 모두 세로 9:16."""
    if aspect == ANCHOR:
        return anchor_prompt(core), "9:16"
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
    for e in generated_entries(channel):
        aspects = {}
        for a in ASPECT_KEYS:
            k = aspect_key(channel, e["role"], a)
            if k in objects:
                aspects[a] = f"{_aspect_url(channel, e['role'], a)}?v={objects[k]}"
        out.append({
            "role": e["role"], "label": e["label"], "subtitle_name": e.get("subtitle_name"),
            "summary": e["summary"], "aspects": aspects, "status": _status(state, e["role"]),
            "active": e.get("active", True),
        })
    return out


def reference_urls(channel: str, role: str, aspects: tuple[str, ...] = ("glow_front", "daily_front")) -> list[str]:
    """영상 단계(2단계)가 읽을 레퍼런스 URL — 현재 바이블로 확정된 캐스트만. 없으면 [].

    기본 = 반전 정면(기준 얼굴) + 평소 정면(장면 모드에 맞춰 골라 쓴다)."""
    if _status(read_state(channel), role) != "approved":
        return []
    objects = _list_objects(channel)
    return [_aspect_url(channel, role, a) for a in aspects if aspect_key(channel, role, a) in objects]


# ── 생성 ─────────────────────────────────────────────────────────────────
def _require(entry: dict | None, channel: str, role: str) -> dict:
    """자동 생성 role 만 통과(업로드 role 은 생성 대상이 아님)."""
    if not entry or entry.get("source", "generate") != "generate":
        raise ValueError(f"자동 생성 캐스트가 아닙니다: {channel}/{role}")
    return entry


def _gen(adapter, prompt: str, ratio: str, local: Path, refs: list[str] | None = None):
    req = ImageGenerationRequest(prompt=prompt, aspect_ratio=ratio, output_path=str(local),
                                 reference_images=refs,
                                 extra_params={"num_images": 1} if refs else None)
    return asyncio.run(adapter.generate(req))


def generate_all(channel: str, role: str, output_dir: str | None = None, on_progress=None) -> dict:
    """기준 얼굴(반전 정면, t2i) → 나머지 7장(Kontext, ref=기준 얼굴). 아스펙트별 부분 성공 허용.

    기준 얼굴이 실패하면 나머지는 만들 수 없으므로 전부 실패로 끝낸다."""
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

    anchor_local = out_dir / f"{ANCHOR}.png"
    prompt, ratio = _aspect_prompt(entry["core"], ANCHOR)
    try:
        res = _gen(t2i, prompt, ratio, anchor_local)
        _upload(anchor_local, channel, role, ANCHOR, res.source_url)
        generated.append(ANCHOR)
    except Exception as e:  # noqa: BLE001
        logger.warning("[shorts-cast] 기준 얼굴 생성 실패(%s/%s) — 나머지 건너뜀: %s", channel, role, e)
        failed = list(ASPECT_KEYS)
        tick()
        return {"generated": generated, "failed": failed}
    tick()
    for key in (k for k in ASPECT_KEYS if k != ANCHOR):
        prompt, ratio = _aspect_prompt(entry["core"], key)
        local = out_dir / f"{key}.png"
        try:
            res = _gen(kontext, prompt, ratio, local, refs=[str(anchor_local)])
            _upload(local, channel, role, key, res.source_url)
            generated.append(key)
        except Exception as e:  # noqa: BLE001
            logger.warning("[shorts-cast] 아스펙트 생성 실패(%s/%s/%s): %s", channel, role, key, e)
            failed.append(key)
        tick()
    return {"generated": generated, "failed": failed}


def regenerate_aspect(channel: str, role: str, aspect: str, output_dir: str | None = None) -> dict:
    """1장만 재생성. 기준 얼굴은 t2i, 나머지는 R2 의 기준 얼굴을 레퍼런스로. 기준을 바꾸면 경고."""
    entry = _require(get_entry(channel, role), channel, role)
    prompt, ratio = _aspect_prompt(entry["core"], aspect)
    out_dir = Path(output_dir or f"output/shorts/cast/{channel}/{role}")
    out_dir.mkdir(parents=True, exist_ok=True)
    local = out_dir / f"{aspect}.png"
    if aspect == ANCHOR:
        t2i = get_image_adapter()
        if not t2i.is_available():
            raise RuntimeError("이미지 어댑터 미설정(WAVESPEED/OPENAI 키) — 기준 얼굴을 생성할 수 없습니다.")
        url = _upload(local, channel, role, ANCHOR, _gen(t2i, prompt, ratio, local).source_url)
        warning = (f"기준 얼굴({ASPECT_LABELS[ANCHOR]})을 다시 만들었어요. 나머지 7장은 이전 얼굴 기준이라 "
                   "어긋날 수 있어요 — 전체 다시 생성을 권장합니다.")
    else:
        kontext = get_kontext_adapter()
        if not kontext.is_available():
            raise RuntimeError("WAVESPEED_API_KEY 미설정 — 레퍼런스 아스펙트를 생성할 수 없습니다.")
        if aspect_key(channel, role, ANCHOR) not in _list_objects(channel):
            raise RuntimeError("기준 얼굴(반전 정면)이 없습니다 — 먼저 전체를 생성하세요.")
        ref = _aspect_url(channel, role, ANCHOR)
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
