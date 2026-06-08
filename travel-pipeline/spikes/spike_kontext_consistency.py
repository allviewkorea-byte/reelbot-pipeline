"""스파이크(검증용 throwaway) — 캐릭터 일관성 PoC.

목적: PR-S2 본 구현 전에 "캐릭터 시트 1장 + FLUX.1 Kontext Pro Multi(WaveSpeed)로
서로 다른 씬을 뽑았을 때 동일 인물·웹툰 스타일이 유지되는가"를 실제 이미지로 확인한다.

이 파일은 프로덕션 파이프라인에 연결되지 않는다. 검증이 끝나면 삭제해도 된다.

동작:
  1) (옵션) 캐릭터 시트 1장 생성 — 웹툰 스타일, 앞/측면 + 표정, 깔끔한 배경
  2) 시트 CDN URL 을 reference 로 flux-kontext-pro/multi 에 넣어 서로 다른 씬 3종 생성
     (씬당 num_images 장씩 → 큐레이션용)
  3) 모든 결과를 output/ 에 저장 + manifest.json + 비용/체크리스트 출력

실행 (로컬, py 사용):
  cd travel-pipeline
  set WAVESPEED_API_KEY=...                      (Windows)   /  export WAVESPEED_API_KEY=...
  py -m pip install httpx                         (미설치 시)
  py spikes/spike_kontext_consistency.py

  # 이미 만든 시트가 있으면 재생성 없이 그 URL 로 바로 씬 생성:
  py spikes/spike_kontext_consistency.py --sheet-url https://.../sheet.png

확인 포인트(육안):
  - 씬 3종에서 얼굴/헤어 형태·색/의상/시그니처(안경·귀걸이)가 동일 인물로 보이는가
  - 웹툰(플랫 컬러·셀 셰이딩) 스타일이 유지되는가
  - 이미지 안에 글자/자막이 들어가지 않았는가 (자막은 합성 단계에서만)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

import httpx

BASE_URL = "https://api.wavespeed.ai/api/v3"
SHEET_MODEL_DEFAULT = "wavespeed-ai/z-image/turbo"  # 시트 생성용(저비용). seedream-v5-lite 로 올려도 됨
KONTEXT_MODEL = "wavespeed-ai/flux-kontext-pro/multi"  # 씬 일관성 엔진

OUT_DIR = Path(__file__).resolve().parent / "output"

# --- 캐릭터 정체성 앵커 -------------------------------------------------------
# 독특할수록 드리프트가 덜 보인다(개성 있는 헤어/시그니처/색 팔레트를 앵커로).
CHARACTER_ANCHOR = (
    "a Korean woman in her early 20s, long wavy auburn hair, round thin-rim glasses, "
    "beige oversized knit cardigan over a white tee, a small gold star-shaped earring"
)

SHEET_PROMPT = (
    "Korean webtoon (manhwa) style character reference sheet of ONE single character. "
    "Clean flat-color digital illustration, soft cel shading, thin clean linework. "
    f"Character: {CHARACTER_ANCHOR}. "
    "Show the SAME character three times on a plain light-gray background: "
    "full-body front view, side profile, and a bust shot with a gentle smile. "
    "Identical face, hairstyle, and outfit across all three. Character turnaround / model sheet. "
    "No text, no labels, no watermark."
)

# 감정·배경이 서로 크게 다른 3개 씬 — 드리프트가 가장 잘 드러나는 조합
SCENES = [
    (
        "scene1_rain_night",
        "standing alone under a streetlight in the rain at night, holding a transparent "
        "umbrella, looking down sadly, three-quarter view, plain dark background",
    ),
    (
        "scene2_crying_room",
        "sitting on the floor of a small dim apartment, hugging knees, crying, warm lamp "
        "light, plain simple background",
    ),
    (
        "scene3_sunny_smile",
        "walking on a bright sunny street, smiling softly in the morning light, plain background",
    ),
]


def _scene_prompt(action: str) -> str:
    return (
        "Korean webtoon (manhwa) style, flat color with soft cel shading. "
        "The SAME character as in the reference image, " + action + ". "
        f"Keep the exact same identity: {CHARACTER_ANCHOR}. "
        "Same face shape, same hair color and style, same glasses, same earring, same outfit. "
        "9:16 vertical composition. No text, no subtitles, no watermark."
    )


async def _submit_and_poll(
    client: httpx.AsyncClient, model_id: str, payload: dict, label: str
) -> dict:
    """제출 → 폴링 공통 루틴. 기존 어댑터와 동일한 WaveSpeed 패턴."""
    api_key = os.environ["WAVESPEED_API_KEY"]
    headers = {"Authorization": f"Bearer {api_key}"}

    submit = await client.post(f"{BASE_URL}/{model_id}", headers=headers, json=payload)
    if submit.status_code >= 400:
        raise RuntimeError(f"[{label}] submit {submit.status_code}: {submit.text}")
    task_id = submit.json()["data"]["id"]
    print(f"  [{label}] task={task_id} 제출됨, 폴링 중...")

    for _ in range(120):  # 최대 ~2분
        await asyncio.sleep(1)
        poll = await client.get(f"{BASE_URL}/predictions/{task_id}/result", headers=headers)
        if poll.status_code >= 400:
            raise RuntimeError(f"[{label}] poll {poll.status_code}: {poll.text}")
        data = poll.json()["data"]
        status = data.get("status")
        if status == "completed":
            return data
        if status == "failed":
            raise RuntimeError(f"[{label}] failed: {data.get('error', data)}")
    raise TimeoutError(f"[{label}] timeout")


async def _download(client: httpx.AsyncClient, url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = await client.get(url)
    resp.raise_for_status()
    dest.write_bytes(resp.content)


async def generate_sheet(client: httpx.AsyncClient, model_id: str) -> str:
    """캐릭터 시트 1장 생성. CDN URL 반환(Kontext images 에 URL 로 넘기기 위함)."""
    payload = {
        "prompt": SHEET_PROMPT,
        "size": "1024*1536",  # 9:16 (z-image/turbo 는 size 파라미터)
        "seed": -1,
        "output_format": "png",
        "enable_base64_output": False,
        "enable_sync_mode": False,
    }
    data = await _submit_and_poll(client, model_id, payload, "sheet")
    url = data["outputs"][0]
    await _download(client, url, OUT_DIR / "00_character_sheet.png")
    print(f"  [sheet] 저장: output/00_character_sheet.png")
    return url


async def generate_scene(
    client: httpx.AsyncClient, name: str, action: str, sheet_url: str, num_images: int, seed: int
) -> list[str]:
    """flux-kontext-pro/multi 로 한 씬을 num_images 장 생성."""
    payload = {
        "prompt": _scene_prompt(action),
        "images": [sheet_url],          # reference 최대 5장 (여기선 시트 1장)
        "aspect_ratio": "9:16",
        "num_images": num_images,
        "output_format": "png",
        "enable_base64_output": False,
        "enable_sync_mode": False,
    }
    if seed >= 0:
        payload["seed"] = seed
    data = await _submit_and_poll(client, KONTEXT_MODEL, payload, name)
    urls = data.get("outputs", [])
    for i, url in enumerate(urls, 1):
        await _download(client, url, OUT_DIR / f"{name}_{i}.png")
    print(f"  [{name}] {len(urls)}장 저장")
    return urls


# Kontext Pro 대략 단가(USD/장) — 정확값은 WaveSpeed 가격표 확인 필요(스파이크 추정).
_KONTEXT_PRICE = 0.04
_SHEET_PRICE = 0.01


async def main() -> None:
    parser = argparse.ArgumentParser(description="캐릭터 일관성 스파이크 (Kontext Pro Multi)")
    parser.add_argument("--sheet-url", help="기존 시트 URL (있으면 시트 재생성 생략)")
    parser.add_argument("--sheet-model", default=SHEET_MODEL_DEFAULT, help="시트 생성 모델")
    parser.add_argument("--num-images", type=int, default=2, help="씬당 생성 장수(큐레이션용)")
    parser.add_argument("--seed", type=int, default=-1, help="고정 seed(>=0). 기본 랜덤")
    args = parser.parse_args()

    if not os.environ.get("WAVESPEED_API_KEY"):
        raise SystemExit("WAVESPEED_API_KEY 가 설정되지 않았습니다. 환경변수로 키를 주세요.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    manifest: dict = {"character_anchor": CHARACTER_ANCHOR, "scenes": {}}

    async with httpx.AsyncClient(timeout=180.0) as client:
        if args.sheet_url:
            sheet_url = args.sheet_url
            print(f"시트 재사용: {sheet_url}")
            sheet_cost = 0.0
        else:
            print("① 캐릭터 시트 생성 중...")
            sheet_url = await generate_sheet(client, args.sheet_model)
            sheet_cost = _SHEET_PRICE
        manifest["sheet_url"] = sheet_url

        print("② 씬 생성 중 (flux-kontext-pro/multi)...")
        scene_count = 0
        for name, action in SCENES:
            urls = await generate_scene(
                client, name, action, sheet_url, args.num_images, args.seed
            )
            manifest["scenes"][name] = urls
            scene_count += len(urls)

    cost = sheet_cost + scene_count * _KONTEXT_PRICE
    manifest["estimated_cost_usd"] = round(cost, 4)
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n" + "=" * 60)
    print(f"완료: 씬 {scene_count}장 + 시트 → {OUT_DIR}")
    print(f"예상 비용(추정): ${cost:.3f} / 소요 {time.time() - t0:.0f}s")
    print("=" * 60)
    print(
        "\n[육안 검증 체크리스트]\n"
        "  [ ] 씬 3종에서 동일 인물로 보이는가 (얼굴/헤어 형태·색)\n"
        "  [ ] 시그니처(안경·별 귀걸이·베이지 가디건)가 유지되는가\n"
        "  [ ] 웹툰(플랫 컬러·셀 셰이딩) 스타일이 유지되는가\n"
        "  [ ] 이미지에 글자/자막이 들어가지 않았는가\n"
        "  [ ] 배경이 깔끔한가(요소 오결합 없음)\n"
        "→ 3장 이상에서 동일 인물이면 PR-S2 방식 GO. 아니면 §3 보조수단(seed 고정/앵커 반복/Max 모델) 검토."
    )


if __name__ == "__main__":
    asyncio.run(main())
