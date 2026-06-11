"""사연 트랙 — 캐릭터 시트 생성·저장 (PR-S2a).

채널/캐릭터 설정값(성별/외모/의상/헤어/액세서리)으로 **웹툰 스타일 캐릭터 시트**를
1회 생성하고 R2에 영구 저장한다. 이 시트는 이후 씬 생성(PR-S2b, FLUX Kontext)에서
reference 로 재사용되어 캐릭터 일관성의 '재료'가 된다.

생성 엔진은 신규 벤더 없이 기존 WaveSpeed 이미지 어댑터를 그대로 재사용한다(스타일은
프롬프트로 강제). 시트는 채널당 1회만 만들면 되므로 Railway 휘발성 파일시스템에
남기지 않고 R2 영구 URL 을 돌려준다(로컬 저장 금지 — 기존 학습).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, fields
from pathlib import Path

from adapters import ImageGenerationRequest, r2_storage
from adapters.image.wavespeed_image_adapter import WavespeedImageAdapter

logger = logging.getLogger(__name__)

# 시트 생성용 기본 모델(저비용). 채널이 더 좋은 모델을 지정하면 그것을 쓴다.
DEFAULT_SHEET_MODEL = "wavespeed-ai/z-image/turbo"

# 공통 그림체/품질 서술어. 시트·씬 프롬프트 양쪽 끝에 붙여 인물을 더 리치하게(반실사
# 일러스트) 만든다. ⚠️ 풀 포토리얼 금지 — FLUX Kontext 일관성이 깨진다. 정체성(성별·
# 나이·헤어·의상 등) 스펙은 절대 바꾸지 않고, 여기서는 그림체/품질/조명 서술어만 더한다.
SAYEON_IMAGE_STYLE = (
    "polished semi-realistic Korean illustration style, soft volumetric lighting, "
    "detailed facial rendering with subtle skin shading and natural blush, "
    "expressive eyes with catchlights, fine individual hair strands, "
    "gentle depth of field, professional webtoon/anime-film finish, high detail, "
    "clean lines with painterly shading"
)

# ── 동물 캐스팅 (사람 → 동물 마스코트 전환) ──────────────────────────────
# 주인공은 항상 흰곰 마스코트(부록 A). 매 컷 프롬프트에 고정 삽입되는 단일 소스.
_POLAR_BEAR_CORE = (
    "a chubby round baby polar bear mascot with short stubby limbs "
    "(NOT adult-bear proportions), cream-white soft fluffy fur, a small round black "
    "nose, small rounded ears, and large round expressive eyes"
)

# 흰곰 그림체(부록 A): 따뜻한 파스텔 2D. 풀 포토리얼/3D 금지.
POLAR_BEAR_ART_STYLE = (
    "warm pastel 2D illustration, soft hand-drawn webtoon storybook style, gentle cel "
    "shading, clean rounded line art, cohesive muted pastel palette, painterly warmth. "
    "NOT photorealistic, NOT 3D, NOT a flat sterile vector"
)

# 사연 톤 → 흰곰 눈 표현 토글.
_BEAR_EYES = {
    "serious": "wearing small round black sunglasses",
    "light": "with big sparkling round black eyes (no sunglasses)",
}

# 캐스팅 팔레트(역할 → 동물, 부록 B). 같은 사연 내 같은 역할은 동일 동물로 일관 유지.
# 주인공 흰곰과 베이스 색·실루엣(귀 모양)이 확실히 달라야 한다.
MALE_LEAD_ANIMAL = "a warm brown shiba-dog"   # 남자 상대(그) — 고정
CASTING_PALETTE = {
    "protagonist": "the white polar bear",          # 화자(주인공)
    "male_lead": MALE_LEAD_ANIMAL,                  # 그
    "female_lead": "a soft cream-colored rabbit",   # 그녀
    "friend": "a small brown squirrel",             # 조연(친구)
    "family": "a gentle large brown bear",          # 가족·어른
    "villain": "a sly raccoon",                     # 얄미운 역
}


def normalize_tone(tone: str | None) -> str:
    """톤 플래그 정규화 — 'serious' | 'light'(기본)."""
    return "serious" if (tone or "").strip().lower() == "serious" else "light"


def build_protagonist_character(tone: str = "light") -> str:
    """흰곰 주인공 CHARACTER 블록(부록 A) — 톤별 눈 표현 토글."""
    return f"{_POLAR_BEAR_CORE}, {_BEAR_EYES[normalize_tone(tone)]}"


def cast_supporting_animal(role: str) -> str:
    """역할 → 상대/조연 동물(부록 B). 같은 역할은 항상 같은 동물(일관성).

    남자 상대(male_lead)는 항상 갈색 시바견. 미상 역할은 친구 기본값.
    """
    key = (role or "").strip().lower().replace(" ", "_")
    return CASTING_PALETTE.get(key, CASTING_PALETTE["friend"])


@dataclass
class CharacterSpec:
    """캐릭터 라이브러리 설정 폼과 1:1 대응하는 캐릭터 명세."""

    gender: str = ""        # 성별 (예: "woman", "man")
    age: str = ""           # 연령대 (예: "early 20s")
    face: str = ""          # 외모/얼굴 특징
    hair: str = ""          # 헤어 (색·길이·스타일)
    outfit: str = ""        # 의상
    accessories: str = ""   # 액세서리
    signature: str = ""     # 시그니처(가장 독특한 정체성 앵커)
    extra: str = ""         # 기타 자유 입력

    @classmethod
    def from_dict(cls, data: dict) -> "CharacterSpec":
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: (data.get(k) or "") for k in allowed})


def build_character_anchor(spec: CharacterSpec, tone: str = "light") -> str:
    """모든 씬 프롬프트에 반복해 넣을 주인공 정체성 앵커.

    주인공은 항상 흰곰 마스코트(동물 캐스팅, 부록 A). 사람 스펙(성별·나이·헤어 등)은
    더 이상 외모로 쓰지 않고, 흰곰 바이블을 단일 소스로 박아 일관성을 유지한다.
    tone: "serious"(검은 선글라스) | "light"(초롱초롱 눈, 기본).
    """
    return build_protagonist_character(tone)


def build_sheet_prompt(spec: CharacterSpec, tone: str = "light") -> str:
    """흰곰 주인공 레퍼런스 시트 프롬프트(따뜻한 파스텔 2D). 이미지에 텍스트는 없음."""
    character = build_protagonist_character(tone)
    return (
        "Character reference sheet (model sheet) of ONE single mascot character. "
        f"Character: {character}. "
        "Show the SAME character three times on a plain light-gray background: "
        "full-body front view, side profile, and a bust shot with a gentle expression. "
        "Identical face, fur, nose, ears, and body proportions across all three. "
        "Character turnaround / model sheet layout. No text, no labels, no watermark. "
        f"{POLAR_BEAR_ART_STYLE}."
    )


def generate_character_sheet(
    channel_id: str,
    spec: CharacterSpec | dict,
    sheet_model: str | None = None,
    output_dir: str | None = None,
    progress_cb=None,
    tone: str = "light",
) -> dict:
    """캐릭터 시트 1장을 생성하고 R2에 올린 뒤 영구 URL·앵커를 반환.

    Returns:
        {
          "channel_id", "sheet_url"(R2 영구 또는 CDN 폴백), "persistent"(bool),
          "anchor"(씬 생성에 재사용), "prompt", "model", "cost_usd"
        }
    """
    if isinstance(spec, dict):
        spec = CharacterSpec.from_dict(spec)

    adapter = WavespeedImageAdapter(model_id=sheet_model or DEFAULT_SHEET_MODEL)
    if not adapter.is_available():
        raise RuntimeError(
            "WAVESPEED_API_KEY 미설정 — 캐릭터 시트를 생성할 수 없습니다."
        )

    out_dir = Path(output_dir or f"output/sayeon/characters/{channel_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    local_path = out_dir / "sheet.png"

    prompt = build_sheet_prompt(spec, tone=tone)
    anchor = build_character_anchor(spec, tone=tone)

    if progress_cb:
        progress_cb(20, "캐릭터 시트 생성 중...")
    request = ImageGenerationRequest(
        prompt=prompt,
        aspect_ratio="9:16",
        output_path=str(local_path),
    )
    result = asyncio.run(adapter.generate(request))

    if progress_cb:
        progress_cb(70, "시트 R2 업로드 중...")
    sheet_url: str | None = None
    persistent = False
    if r2_storage.is_available():
        try:
            sheet_url = r2_storage.upload_character_sheet(str(local_path), channel_id)
            persistent = True
        except Exception as e:  # noqa: BLE001
            logger.warning("시트 R2 업로드 실패, CDN URL 로 폴백: %s", e)
    if not sheet_url:
        # R2 미설정/실패 → WaveSpeed CDN URL 폴백(임시). 운영에선 R2 필수.
        sheet_url = result.source_url
        logger.warning(
            "시트가 R2에 영구 저장되지 않았습니다(임시 CDN URL). R2_* 환경변수를 설정하세요."
        )

    if progress_cb:
        progress_cb(100, "완료")
    return {
        "channel_id": channel_id,
        "sheet_url": sheet_url,
        "persistent": persistent,
        "anchor": anchor,
        "prompt": prompt,
        "model": adapter.name,
        "cost_usd": adapter.cost_per_image,
    }
