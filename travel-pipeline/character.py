import base64
from pathlib import Path
from openai import OpenAI
from config import Config, BangkokSpot

# 캐릭터 시드 3방향 정의
_SEED_VIEWS = [
    {
        "key": "front",
        "filename": "front.png",
        "angle": "front view, facing the camera directly",
    },
    {
        "key": "side",
        "filename": "side.png",
        "angle": "side view, facing left, 90 degree profile",
    },
    {
        "key": "back",
        "filename": "back.png",
        "angle": "back view, facing away from the camera",
    },
]

_SEED_BASE_PROMPT = (
    "Same Korean woman in her late 20s, trendy street fashion, "
    "long wavy dark hair, {angle}, full body, photorealistic, "
    "white studio background, sharp lighting, high detail."
)


def _generate_single_image(client: OpenAI, prompt: str) -> bytes:
    response = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1024x1536",
        quality="high",
        n=1,
    )
    return base64.b64decode(response.data[0].b64_json)


def generate_character_seeds(config: Config) -> dict[str, Path]:
    """
    GPT-4o로 동일 캐릭터의 정면/측면/뒷모습 시드 이미지 3장 생성.
    {key: Path} 딕셔너리 반환. 예: {"front": Path(...), "side": ..., "back": ...}
    이미 존재하면 재생성하지 않고 캐시 반환.
    """
    client = OpenAI(api_key=config.openai_api_key)
    seeds_dir = Path(config.images_dir) / "seeds"
    seeds_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, Path] = {}

    for view in _SEED_VIEWS:
        out_path = seeds_dir / view["filename"]

        if out_path.exists():
            print(f"  [character] 시드 캐시 사용: {view['filename']}")
            results[view["key"]] = out_path
            continue

        prompt = _SEED_BASE_PROMPT.format(angle=view["angle"])
        print(f"  [character] 시드 생성 중: {view['filename']} ({view['angle']})")

        image_bytes = _generate_single_image(client, prompt)
        out_path.write_bytes(image_bytes)
        results[view["key"]] = out_path
        print(f"  [character] 저장 완료: {out_path}")

    return results


def generate_character_image(spot: BangkokSpot, config: Config) -> Path:
    """
    GPT-4o (gpt-image-1)로 캐릭터가 해당 관광지에 있는 이미지 생성.
    시드 3장이 없으면 먼저 생성한다.
    """
    client = OpenAI(api_key=config.openai_api_key)

    # 시드가 없으면 최초 1회만 생성
    seeds_dir = Path(config.images_dir) / "seeds"
    if not seeds_dir.exists() or not any(seeds_dir.glob("*.png")):
        print(f"  [character] 캐릭터 시드 이미지 없음 — 3장 생성 시작")
        generate_character_seeds(config)

    prompt = (
        f"{config.character_prompt} "
        f"She is visiting {spot.name_en} in Bangkok, Thailand. "
        f"The background shows the iconic scenery of {spot.name_en}. "
        f"She is posing naturally as a travel influencer. "
        f"Vertical composition suitable for mobile (9:16 ratio). "
        f"Vibrant travel photography style."
    )

    print(f"  [character] {spot.name_ko} 캐릭터 이미지 생성 중...")

    image_bytes = _generate_single_image(client, prompt)
    out_path = Path(config.images_dir) / f"{spot.id}_character.png"
    out_path.write_bytes(image_bytes)

    print(f"  [character] 저장 완료: {out_path}")
    return out_path
