import base64
import shutil
from pathlib import Path
from openai import OpenAI
from config import Config, BangkokSpot

_SEED_VIEWS = [
    {"key": "front", "filename": "front.png", "angle": "front view, facing the camera directly"},
    {"key": "side",  "filename": "side.png",  "angle": "side view, facing left, 90 degree profile"},
    {"key": "back",  "filename": "back.png",  "angle": "back view, facing away from the camera"},
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
        print(f"  [character] 시드 생성 중: {view['filename']}")
        image_bytes = _generate_single_image(client, prompt)
        out_path.write_bytes(image_bytes)
        results[view["key"]] = out_path
    return results


def generate_character_image(spot: BangkokSpot, config: Config) -> Path:
    """
    캐릭터 이미지 반환.
    우선순위:
      1. 이미 생성된 캐시 파일 (재실행 시 비용 0원)
      2. 라이브러리 이미지 (character_library_front 설정 시 비용 0원)
      3. GPT-image-1 생성 (위 둘 다 없을 때만)
    """
    out_path = Path(config.images_dir) / f"{spot.id}_character.png"

    # 1. 캐시 확인
    if out_path.exists():
        print(f"  [character] 캐시 사용: {out_path.name}")
        return out_path

    # 2. 라이브러리 이미지 사용 (config에 경로 설정된 경우)
    lib_image = getattr(config, "character_library_front", None)
    if lib_image and Path(lib_image).exists():
        shutil.copy(lib_image, out_path)
        print(f"  [character] 라이브러리 이미지 사용: {out_path.name}")
        return out_path

    # 3. GPT 생성 (비용 발생)
    client = OpenAI(api_key=config.openai_api_key)

    seeds_dir = Path(config.images_dir) / "seeds"
    if not seeds_dir.exists() or not any(seeds_dir.glob("*.png")):
        generate_character_seeds(config)

    prompt = (
        f"{config.character_prompt} "
        f"She is visiting {spot.name_en} in Bangkok, Thailand. "
        f"The background shows the iconic scenery of {spot.name_en}. "
        f"She is posing naturally as a travel influencer. "
        f"Vertical composition suitable for mobile (9:16 ratio). "
        f"Vibrant travel photography style."
    )

    print(f"  [character] {spot.name_ko} 캐릭터 이미지 생성 중... (비용 발생)")
    image_bytes = _generate_single_image(client, prompt)
    out_path.write_bytes(image_bytes)
    print(f"  [character] 저장 완료: {out_path}")
    return out_path