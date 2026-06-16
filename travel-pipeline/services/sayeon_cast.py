"""사연 동물 캐스트 — 캐릭터 시트 관리 화면(프론트 /cast)용 백엔드 서비스.

8캐스트(바이블)를 역할(role) 단위로 정의하고, 캐릭터별 **멀티 아스펙트 세트**(정면 +
반측면 + 측면 + 표정 4종 = 7장)를 생성해 R2(cast/{role}/{aspect}.png)에 저장한다.

일관성 핵심: **정면을 먼저 t2i 로 만들고**, 나머지 6장은 그 정면을 **레퍼런스 이미지**로
Kontext(멀티레퍼런스 배관, PR#141)에 넣어 생성한다 → 같은 캐릭터 유지.

⚠️ 실제 씬 멀티레퍼런스(sayeon_scene) 연결·CASTING_PALETTE 정합은 이번 범위가 아니다.
여기서는 "역할 → 동물 → R2 아스펙트 키" 컨벤션과 생성/조회만 담당한다.

생성 엔진은 신규 벤더 없이 기존 어댑터를 재사용한다(정면=z-image t2i, 나머지=Kontext).
시트는 Railway 휘발성 파일시스템에 남기지 않고 R2 영구 URL 을 돌려준다.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from adapters import (
    ImageGenerationRequest,
    get_image_adapter,
    get_kontext_adapter,
    r2_storage,
)
from services.sayeon_character import (
    POLAR_BEAR_ART_STYLE,
    _BROWN_BEAR_CORE,
    build_protagonist_character,
)

logger = logging.getLogger(__name__)

# ── 아스펙트 정의 ────────────────────────────────────────────────────────
# 정면(front)은 t2i 로 먼저 생성, 나머지는 정면을 레퍼런스로 Kontext 생성.
# (aspect_key, 시점/표정 묘사). 키는 R2 cast/{role}/{key}.png 로 고정.
_VIEW_ASPECTS: list[tuple[str, str]] = [
    ("threequarter", "three-quarter (3/4) view, the body turned about 45 degrees"),
    ("side", "side profile view, the body turned 90 degrees to the side"),
]
_EXPR_ASPECTS: list[tuple[str, str]] = [
    ("expr_joy", "joyful and happy — a big bright smile and sparkling crescent eyes"),
    ("expr_sad", "sad — teary downturned eyes, drooping mouth and posture"),
    ("expr_angry", "angry — furrowed brows, a frown, tense and grumpy"),
    ("expr_surprised", "surprised — wide round eyes and a small open mouth, startled"),
]
# 생성·조회 순서(고정). front 가 항상 선두(레퍼런스 소스).
ASPECT_KEYS: list[str] = ["front", *(k for k, _ in _VIEW_ASPECTS), *(k for k, _ in _EXPR_ASPECTS)]


# ── 캐스트 바이블 (역할 → 동물 / 성격 / 프롬프트 코어 / 색 / 상대 키) ──────
# core 는 프롬프트가 감싸는 캐릭터 묘사(눈 표현 포함). colors=핵심 색 hex(메타데이터,
# 디자인 토큰 아님). relative_height=캐릭터 간 상대 키(float, 갈색곰 1.0 기준).
CAST_BIBLE: list[dict] = [
    {
        "role": "protagonist",
        "name": "흰곰 · 주인공",
        "animal": "흰곰",
        "personality": "평범하고 공감되는 '나'. 사연을 이끄는 1인칭 화자.",
        "core": build_protagonist_character("light"),
        "colors": ["#FAF6EF", "#EAE0D0", "#2B2B2B", "#1A1A1A"],
        "relative_height": 0.85,
    },
    {
        "role": "narrator",
        "name": "흰곰 · 전지모드",
        "animal": "흰곰(선글라스)",
        "personality": "쿨한 해설자. 내레이션과 반전 폭로를 담당.",
        "core": build_protagonist_character("serious"),
        "colors": ["#FAF6EF", "#EAE0D0", "#1A1A1A"],
        "relative_height": 0.85,
    },
    {
        "role": "male_lead",
        "name": "시바견 · 그",
        "animal": "시바견",
        "personality": "남성 상대역 또는 남성 가해자.",
        "core": (
            "a chubby round shiba-dog mascot with short stubby limbs "
            "(NOT realistic-dog proportions), warm tan-and-cream fur, small pointed "
            "perky ears, a small black nose, and round dark expressive eyes"
        ),
        "colors": ["#D9A066", "#F2E2C9", "#3A2A1A"],
        "relative_height": 0.8,
    },
    {
        "role": "female_lead",
        "name": "토끼 · 그녀",
        "animal": "토끼",
        "personality": "여성 상대역 또는 여성 가해자.",
        "core": (
            "a chubby round rabbit mascot with short stubby limbs, soft cream-colored "
            "fur, long upright ears, a tiny pink nose, and large round expressive eyes"
        ),
        "colors": ["#F5EAD9", "#E9D5C0", "#E59AA8", "#2B2B2B"],
        "relative_height": 0.55,
    },
    {
        "role": "friend_squirrel",
        "name": "다람쥐 · 친구",
        "animal": "다람쥐",
        "personality": "활발한 정보통. 사이다 같은 친구.",
        "core": (
            "a chubby round squirrel mascot with short stubby limbs, warm "
            "reddish-brown fur, a big fluffy tail, small tufted ears, and bright "
            "lively round eyes"
        ),
        "colors": ["#B5651D", "#8C4A12", "#F2E2C9"],
        "relative_height": 0.4,
    },
    {
        "role": "friend_penguin",
        "name": "펭귄 · 친구",
        "animal": "펭귄",
        "personality": "차분하고 의리 있는 친구. 끝에 진심을 보인다.",
        "core": (
            "a chubby round baby penguin mascot with short stubby flippers, "
            "black-and-white plumage, a small round orange beak, and calm round "
            "dark eyes"
        ),
        "colors": ["#2B2B2B", "#FFFFFF", "#F2A03D"],
        "relative_height": 0.5,
    },
    {
        "role": "family_bear",
        "name": "갈색곰 · 가족",
        "animal": "갈색곰",
        "personality": "부모·시댁 등 가족. 따뜻하지만 갈등의 진원.",
        "core": _BROWN_BEAR_CORE,
        "colors": ["#8B5A2B", "#6F4520", "#2B2B2B"],
        "relative_height": 1.0,
    },
    {
        "role": "villain",
        "name": "너구리 · 악역",
        "animal": "너구리",
        "personality": "교활한 외부 빌런. 진상·갑질·사기.",
        "core": (
            "a chubby round raccoon mascot with short stubby limbs, gray fur with a "
            "dark mask marking around the eyes, a ringed bushy tail, small rounded "
            "ears, and narrow sly eyes"
        ),
        "colors": ["#9AA0A6", "#5A5F64", "#2B2B2B", "#C9CDD2"],
        "relative_height": 0.7,
    },
]

# role → bible 엔트리(빠른 조회).
_CAST_BY_ROLE = {entry["role"]: entry for entry in CAST_BIBLE}


def get_cast_entry(role: str) -> dict | None:
    """역할 키로 캐스트 바이블 엔트리를 찾는다(없으면 None)."""
    return _CAST_BY_ROLE.get((role or "").strip().lower())


# ── 프롬프트 빌더 ────────────────────────────────────────────────────────
def _front_prompt(core: str) -> str:
    """정면(t2i) — 단일 캐릭터 전신 정면(레퍼런스 소스). 텍스트 없음."""
    return (
        "Full-body FRONT view of ONE single mascot character on a plain light-gray "
        f"background. Character: {core}. Facing the camera directly, neutral friendly "
        "expression, standing, the whole body visible head to toe with margin. "
        f"{POLAR_BEAR_ART_STYLE}. No text, no labels, no watermark."
    )


def _view_prompt(core: str, view_desc: str) -> str:
    """시점 변경(Kontext, reference=정면) — 시점만 바꾸고 정체성 유지."""
    return (
        "Using the reference image as the EXACT same character, render the SAME single "
        f"mascot in a {view_desc}. Character: {core}. Keep identical fur color, markings, "
        "nose, ears, body proportions and features as the reference — change ONLY the "
        "viewing angle. Full body on a plain light-gray background. "
        f"{POLAR_BEAR_ART_STYLE}. No text, no labels, no watermark."
    )


def _expr_prompt(core: str, expr_desc: str) -> str:
    """표정 변경(Kontext, reference=정면) — 얼굴 중심, 표정만 변경."""
    return (
        "Using the reference image as the EXACT same character, render the SAME single "
        "mascot as a front-facing head-and-shoulders (bust) close-up with this facial "
        f"expression: {expr_desc}. Character: {core}. Keep identical fur color, markings, "
        "nose, ears and features as the reference — change ONLY the facial expression. "
        f"Plain light-gray background. {POLAR_BEAR_ART_STYLE}. No text, no labels, no watermark."
    )


def _public_entry(entry: dict) -> dict:
    """프론트로 내려줄 캐스트 1건(프롬프트 코어 제외, R2 아스펙트 URL 병합).

    sheet_url = 정면(front) 아스펙트(대표 썸네일, 하위호환). aspects = 아스펙트별 URL.
    """
    aspects: dict[str, str] = {}
    if r2_storage.is_available():
        for key in ASPECT_KEYS:
            if r2_storage.cast_aspect_exists(entry["role"], key):
                aspects[key] = r2_storage.cast_aspect_url(entry["role"], key)
    return {
        "role": entry["role"],
        "name": entry["name"],
        "animal": entry["animal"],
        "personality": entry["personality"],
        "colors": entry["colors"],
        "relative_height": entry["relative_height"],
        "aspects": aspects,
        "sheet_url": aspects.get("front"),  # 대표 썸네일(하위호환)
    }


def list_cast(channel_id: str = "") -> list[dict]:
    """8캐스트 메타 + 아스펙트 URL + colors + relative_height. status 는 프론트가 병합.

    channel_id 는 하위호환용(아스펙트 키는 채널 무관이라 사용하지 않음).
    """
    return [_public_entry(entry) for entry in CAST_BIBLE]


def _persist_aspect(local_path: Path, role: str, aspect: str, source_url: str | None) -> str:
    """로컬 아스펙트를 R2(cast/{role}/{aspect}.png)에 올리고 URL 반환. 실패 시 CDN 폴백."""
    if r2_storage.is_available():
        try:
            return r2_storage.upload_cast_aspect(str(local_path), role, aspect)
        except Exception as e:  # noqa: BLE001
            logger.warning("캐스트 아스펙트 R2 업로드 실패(%s/%s), CDN 폴백: %s", role, aspect, e)
    if source_url:
        logger.warning("아스펙트 %s/%s 가 R2에 영구 저장되지 않음(임시 CDN URL).", role, aspect)
        return source_url
    raise RuntimeError(f"아스펙트 {role}/{aspect} 저장 실패(R2 미설정·CDN 없음)")


def generate_cast_aspects(role: str, output_dir: str | None = None) -> dict:
    """역할별 멀티 아스펙트(정면+반측면+측면+표정4)를 생성하고 R2에 저장한다.

    정면을 먼저 t2i 로 생성하고, 그 정면을 레퍼런스로 나머지 6장을 Kontext 로 만든다.
    아스펙트별로 try/except — 일부 실패해도 나머지는 계속·저장(부분 성공 허용).

    Returns:
        {"role","name","animal","filename","aspects":{key:url},
         "generated":[key...],"failed":[key...],"colors","relative_height"}
    정면 생성 자체가 실패하면 의존 아스펙트는 건너뛴다(전부 failed).
    """
    entry = get_cast_entry(role)
    if not entry:
        raise ValueError(f"알 수 없는 캐스트 역할입니다: {role}")

    core: str = entry["core"]
    t2i = get_image_adapter()
    if not t2i.is_available():
        raise RuntimeError("이미지 어댑터 미설정(WAVESPEED/OPENAI 키) — 정면을 생성할 수 없습니다.")
    kontext = get_kontext_adapter()
    if not kontext.is_available():
        raise RuntimeError("WAVESPEED_API_KEY 미설정 — 레퍼런스 아스펙트를 생성할 수 없습니다.")

    out_dir = Path(output_dir or f"output/sayeon/cast/{role}")
    out_dir.mkdir(parents=True, exist_ok=True)

    aspects: dict[str, str] = {}
    generated: list[str] = []
    failed: list[str] = []

    # ① 정면(t2i) — 레퍼런스 소스. 실패 시 의존 아스펙트 전부 건너뜀.
    front_local = out_dir / "front.png"
    try:
        result = asyncio.run(
            t2i.generate(
                ImageGenerationRequest(
                    prompt=_front_prompt(core),
                    aspect_ratio="9:16",
                    output_path=str(front_local),
                )
            )
        )
        aspects["front"] = _persist_aspect(front_local, role, "front", result.source_url)
        generated.append("front")
    except Exception as e:  # noqa: BLE001
        logger.warning("정면 생성 실패(%s) — 의존 아스펙트 건너뜀: %s", role, e)
        failed = list(ASPECT_KEYS)
        return {
            "role": entry["role"], "name": entry["name"], "animal": entry["animal"],
            "filename": "front.png", "aspects": aspects, "sheet_url": None,
            "generated": generated, "failed": failed,
            "colors": entry["colors"], "relative_height": entry["relative_height"],
        }

    # ② 정면을 레퍼런스로 시점 변경 + 표정 변경 6장. 각각 독립 try(부분 성공 허용).
    jobs: list[tuple[str, str]] = [
        *((key, _view_prompt(core, desc)) for key, desc in _VIEW_ASPECTS),
        *((key, _expr_prompt(core, desc)) for key, desc in _EXPR_ASPECTS),
    ]
    for key, prompt in jobs:
        local = out_dir / f"{key}.png"
        try:
            result = asyncio.run(
                kontext.generate(
                    ImageGenerationRequest(
                        prompt=prompt,
                        reference_images=[str(front_local)],
                        aspect_ratio="1:1" if key.startswith("expr_") else "9:16",
                        output_path=str(local),
                        extra_params={"num_images": 1},
                    )
                )
            )
            aspects[key] = _persist_aspect(local, role, key, result.source_url)
            generated.append(key)
        except Exception as e:  # noqa: BLE001
            logger.warning("아스펙트 생성 실패(%s/%s): %s", role, key, e)
            failed.append(key)

    return {
        "role": entry["role"],
        "name": entry["name"],
        "animal": entry["animal"],
        "filename": "front.png",  # 대표(하위호환)
        "aspects": aspects,
        "sheet_url": aspects.get("front"),  # 대표 썸네일(하위호환)
        "generated": generated,
        "failed": failed,
        "colors": entry["colors"],
        "relative_height": entry["relative_height"],
    }
