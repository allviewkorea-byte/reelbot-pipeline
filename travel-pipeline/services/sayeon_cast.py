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
import threading
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
# 배경은 중립(균일 light-gray 스튜디오) — ①에서 검증된 결. 다크 카드 위에서도
# 기존 /character(human) 라이브러리와 동일하게 깔끔히 읽힌다. (크로마키/누끼는 보류:
# rembg=onnxruntime+모델 런타임 다운로드·추론 메모리로 라이브 영상 파이프라인 OOM 위험.)
_NEUTRAL_BG = (
    "a plain soft uniform light-gray studio background, evenly lit, "
    "no gradient, no shadow, no props"
)


def _front_prompt(core: str) -> str:
    """정면(t2i) — 단일 캐릭터 전신 정면(레퍼런스 소스). 텍스트 없음."""
    return (
        f"Full-body FRONT view of ONE single mascot character on {_NEUTRAL_BG}. "
        f"Character: {core}. Facing the camera directly, neutral friendly "
        "expression, standing, the whole body visible head to toe with margin. "
        f"{POLAR_BEAR_ART_STYLE}. No text, no labels, no watermark."
    )


def _view_prompt(core: str, view_desc: str) -> str:
    """시점 변경(Kontext, reference=정면) — 시점만 바꾸고 정체성 유지."""
    return (
        "Using the reference image as the EXACT same character, render the SAME single "
        f"mascot in a {view_desc}. Character: {core}. Keep identical fur color, markings, "
        "nose, ears, body proportions and features as the reference — change ONLY the "
        f"viewing angle. Full body on {_NEUTRAL_BG}. "
        f"{POLAR_BEAR_ART_STYLE}. No text, no labels, no watermark."
    )


def _expr_prompt(core: str, expr_desc: str) -> str:
    """표정 변경(Kontext, reference=정면) — 얼굴 중심, 표정만 변경."""
    return (
        "Using the reference image as the EXACT same character, render the SAME single "
        "mascot as a front-facing head-and-shoulders (bust) close-up with this facial "
        f"expression: {expr_desc}. Character: {core}. Keep identical fur color, markings, "
        "nose, ears and features as the reference — change ONLY the facial expression. "
        f"Background: {_NEUTRAL_BG}. {POLAR_BEAR_ART_STYLE}. No text, no labels, no watermark."
    )


def _public_entry(entry: dict, objects: dict[str, int]) -> dict:
    """프론트로 내려줄 캐스트 1건(프롬프트 코어 제외, R2 아스펙트 URL 병합).

    objects = R2 cast/ 아래 {키: LastModified epoch}(list_cast 가 1회 조회해 공유).
    56회 head_object 대신 메모리 멤버십으로 판정하고, URL 끝에 ?v=<epoch> 를 붙여
    같은 키 덮어쓰기 후에도 브라우저/CDN 이 옛 이미지를 서빙하지 않게 한다(캐시 버스팅).
    sheet_url = 정면(front) 아스펙트(대표 썸네일, 하위호환). aspects = 아스펙트별 URL.
    """
    aspects: dict[str, str] = {}
    for key in ASPECT_KEYS:
        obj_key = f"cast/{entry['role']}/{key}.png"
        if obj_key in objects:
            url = r2_storage.cast_aspect_url(entry["role"], key)
            aspects[key] = f"{url}?v={objects[obj_key]}"  # LastModified 기반 캐시 버스팅
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

    R2 키를 1회(list_objects_v2)만 조회해 8×7=56 head_object 를 없앤다(속도 개선).
    같은 조회로 LastModified 를 받아 URL 캐시 버스팅(?v=)에 쓴다.
    channel_id 는 하위호환용(아스펙트 키는 채널 무관이라 사용하지 않음).
    """
    objects = r2_storage.list_cast_objects()
    return [_public_entry(entry, objects) for entry in CAST_BIBLE]


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


def generate_cast_aspects(
    role: str, output_dir: str | None = None, on_progress=None
) -> dict:
    """역할별 멀티 아스펙트(정면+반측면+측면+표정4)를 생성하고 R2에 저장한다.

    정면을 먼저 t2i 로 생성하고, 그 정면을 레퍼런스로 나머지 6장을 Kontext 로 만든다.
    아스펙트별로 try/except — 일부 실패해도 나머지는 계속·저장(부분 성공 허용).
    on_progress(generated, failed): 아스펙트 1개 완료/실패마다 호출(진행상태 폴링용).

    Returns:
        {"role","name","animal","filename","aspects":{key:url},
         "generated":[key...],"failed":[key...],"colors","relative_height"}
    정면 생성 자체가 실패하면 의존 아스펙트는 건너뛴다(전부 failed).
    """
    def _tick(generated: list[str], failed: list[str]) -> None:
        if on_progress:
            try:
                on_progress(list(generated), list(failed))
            except Exception:  # noqa: BLE001 - 진행 콜백 오류는 생성에 영향 주지 않음
                pass
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
        _tick(generated, failed)
    except Exception as e:  # noqa: BLE001
        logger.warning("정면 생성 실패(%s) — 의존 아스펙트 건너뜀: %s", role, e)
        failed = list(ASPECT_KEYS)
        _tick(generated, failed)
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
        _tick(generated, failed)

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


# ── 비동기 생성 진행상태(인메모리) ──────────────────────────────────────
# 멀티 아스펙트 생성은 수십 초~수 분이라 BackgroundTasks 로 논블로킹 실행하고,
# 진행상태를 역할별 인메모리 dict 에 적재한다. ⚠️ Railway 재시작 시 소실(JobManager 와
# 동일한 MVP 한계) — 단, 아스펙트 자체는 R2 에 영구 저장되므로 새로고침으로 복구된다.
ASPECT_TOTAL = len(ASPECT_KEYS)  # 7
_PROGRESS_LOCK = threading.Lock()
_PROGRESS: dict[str, dict] = {}


def _set_progress(role: str, **kw) -> None:
    with _PROGRESS_LOCK:
        cur = _PROGRESS.get(role) or {
            "status": "idle", "generated": [], "failed": [], "total": ASPECT_TOTAL,
        }
        cur.update(kw)
        cur["total"] = ASPECT_TOTAL
        _PROGRESS[role] = cur


def get_cast_progress(role: str) -> dict:
    """역할별 생성 진행상태. 없으면 idle. status: idle|running|done|failed."""
    with _PROGRESS_LOCK:
        cur = _PROGRESS.get(role)
        if not cur:
            return {
                "role": role, "status": "idle",
                "generated": [], "failed": [], "total": ASPECT_TOTAL,
            }
        return {
            "role": role,
            "status": cur["status"],
            "generated": list(cur["generated"]),
            "failed": list(cur["failed"]),
            "total": cur["total"],
        }


def run_cast_generation(role: str) -> None:
    """BackgroundTasks 진입점 — 진행상태를 갱신하며 멀티 아스펙트를 생성한다.

    role 검증은 호출부(라우트)에서 끝났다고 가정. 1장이라도 성공하면 done,
    전무하면 failed. 부분 실패는 failed 목록으로 노출된다.
    """
    _set_progress(role, status="running", generated=[], failed=[])

    def cb(generated: list[str], failed: list[str]) -> None:
        _set_progress(role, generated=generated, failed=failed)

    try:
        result = generate_cast_aspects(role, on_progress=cb)
        status = "done" if result["generated"] else "failed"
        _set_progress(
            role, status=status,
            generated=result["generated"], failed=result["failed"],
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("캐스트 생성 백그라운드 실패(%s): %s", role, e)
        _set_progress(role, status="failed")
