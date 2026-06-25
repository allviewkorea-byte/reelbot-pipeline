import asyncio
from pathlib import Path
import anthropic
import edge_tts
from config import Config, BangkokSpot, BANGKOK_SPOTS, CLAUDE_MODEL

def generate_script(spots: list[BangkokSpot], config: Config) -> dict[str, str]:
    """
    Claude API로 각 관광지 나레이션 스크립트 생성.
    캐릭터가 직접 말하는 1인칭 여행 브이로그 스타일.
    """
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    spot_list = "\n".join(
        f"- {s.name_ko} ({s.name_en}): {s.description_ko}" for s in spots
    )

    system_prompt = (
        "너는 방콕을 여행하는 트렌디한 한국 여성 여행 유튜버야. "
        "밝고 친근한 말투로, 짧고 임팩트 있게 말해. "
        "각 관광지마다 15초 분량(약 60~80자)의 나레이션을 작성해. "
        "자연스러운 구어체를 사용하고, 감탄사와 감정 표현을 적절히 넣어줘. "
        "JSON 형식으로만 응답해. 예: {\"장소ID\": \"나레이션 텍스트\"}"
    )

    user_prompt = (
        f"다음 방콕 관광지들에 대해 각각 나레이션을 작성해줘:\n\n{spot_list}\n\n"
        f"장소 ID: {', '.join(s.id for s in spots)}\n"
        f"JSON 형식으로 장소 ID를 키로 해서 반환해줘."
    )

    print("  [narration] Claude로 나레이션 스크립트 생성 중...")

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": user_prompt}],
        system=system_prompt,
    )

    import json
    raw = message.content[0].text.strip()
    # 마크다운 코드블록 제거
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    scripts = json.loads(raw.strip())

    print(f"  [narration] 스크립트 생성 완료: {list(scripts.keys())}")
    return scripts


async def _synthesize_tts(text: str, voice: str, rate: str, out_path: Path):
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(out_path))


def generate_audio(
    spot: BangkokSpot,
    script: str,
    config: Config,
) -> Path:
    """
    Edge TTS로 나레이션 음성 파일 생성 (MP3).
    """
    print(f"  [narration] {spot.name_ko} 음성 변환 중...")

    out_path = Path(config.audio_dir) / f"{spot.id}_narration.mp3"
    asyncio.run(
        _synthesize_tts(script, config.tts_voice, config.tts_rate, out_path)
    )

    print(f"  [narration] 저장 완료: {out_path}")
    return out_path


def generate_intro_outro_script(config: Config) -> dict[str, str]:
    """인트로/아웃트로 나레이션 생성."""
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": (
                "방콕 여행 유튜브 영상의 인트로(약 20초, 90~100자)와 "
                "아웃트로(약 10초, 45~50자)를 작성해줘. "
                "밝고 트렌디한 한국 여성 여행 유튜버 말투로. "
                "JSON 형식: {\"intro\": \"...\", \"outro\": \"...\"}"
            )
        }],
    )

    import json
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())
