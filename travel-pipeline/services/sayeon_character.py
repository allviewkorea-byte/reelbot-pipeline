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


def build_character_anchor(spec: CharacterSpec) -> str:
    """모든 씬 프롬프트에 반복해 넣을 짧은 정체성 앵커 문구를 구성.

    독특한 헤어/시그니처/색을 '정체성 앵커'로 박을수록 드리프트가 덜 보인다(§3).
    """
    subject = " ".join(p for p in (spec.age, spec.gender) if p).strip() or "character"
    details = [
        d.strip()
        for d in (spec.hair, spec.face, spec.outfit, spec.accessories, spec.signature)
        if d and d.strip()
    ]
    anchor = subject if not details else f"{subject}, " + ", ".join(details)
    if spec.extra and spec.extra.strip():
        anchor = f"{anchor}, {spec.extra.strip()}"
    return anchor


def build_sheet_prompt(spec: CharacterSpec) -> str:
    """웹툰 스타일 캐릭터 레퍼런스 시트 프롬프트. 이미지에 텍스트는 넣지 않는다."""
    anchor = build_character_anchor(spec)
    return (
        "Korean webtoon (manhwa) style character reference sheet of ONE single character. "
        "Clean flat-color digital illustration, soft cel shading, thin clean linework. "
        f"Character: {anchor}. "
        "Show the SAME character three times on a plain light-gray background: "
        "full-body front view, side profile, and a bust shot with a gentle smile. "
        "Identical face, hairstyle, and outfit across all three. "
        "Character turnaround / model sheet layout. "
        "No text, no labels, no watermark."
    )


def generate_character_sheet(
    channel_id: str,
    spec: CharacterSpec | dict,
    sheet_model: str | None = None,
    output_dir: str | None = None,
    progress_cb=None,
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

    prompt = build_sheet_prompt(spec)
    anchor = build_character_anchor(spec)

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
