"""검증용 throwaway — 사연 오케스트레이션 end-to-end 검증 (서비스 직접 호출).

샘플 사연 대본 + 샘플 character_spec 으로 generate_full 을 직접 호출해 실제
영상 + 썸네일을 만든다.

⚠️ 실제 API 라 모든 키 필요: OPENAI_API_KEY(분할·후킹), WAVESPEED_API_KEY(시트·씬),
SUPERTONE_API_KEY(TTS, 없으면 Edge 폴백) + ffmpeg. 몇 분 + 소액 비용 발생.

실행:
  cd travel-pipeline
  export OPENAI_API_KEY=...  WAVESPEED_API_KEY=...  [SUPERTONE_API_KEY=...]
  # (선택) R2_* 주면 산출물이 R2 URL, 없으면 로컬 경로
  py spikes/verify_sayeon_orchestrate.py
  # 이미 만든 시트 재사용(시트 생성·비용 스킵):
  py spikes/verify_sayeon_orchestrate.py --sheet-url https://.../sheet.png --anchor "early 20s woman, ..."
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: BLE001
    pass

from services.sayeon_orchestrate import generate_full  # noqa: E402

SAMPLE_SCRIPT = """
스무 살 때, 저는 엄마의 낡은 코트가 부끄러웠어요.
친구들 앞에서 엄마가 그 코트를 입고 오면 모른 척했죠.
한참 뒤, 엄마의 서랍에서 낡은 가계부를 발견했어요.
거기엔 제 학원비와 등록금이 빼곡히 적혀 있었어요.
그제야 저는 부끄러운 게 코트가 아니라 저였다는 걸 알았어요.
당신은 부모님의 낡은 옷에 담긴 의미를, 너무 늦게 알아버린 적 없나요?
"""

SAMPLE_CHARACTER = {
    "gender": "woman",
    "age": "early 20s",
    "hair": "long wavy auburn hair",
    "outfit": "beige oversized knit cardigan over a white tee",
    "accessories": "round thin-rim glasses, a small gold star-shaped earring",
    "signature": "round glasses + star earring + auburn waves",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="사연 오케스트레이션 end-to-end 검증")
    parser.add_argument("--sheet-url", default="", help="기존 시트 URL(주면 시트 생성 스킵)")
    parser.add_argument("--anchor", default="", help="--sheet-url 사용 시 정체성 앵커")
    parser.add_argument("--num-scenes", type=int, default=6, help="씬 개수")
    parser.add_argument("--voice-id", default=None, help="Supertone voice_id(선택)")
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY 필요 (씬 분할·썸네일 후킹)")
    if not os.getenv("WAVESPEED_API_KEY"):
        raise SystemExit("WAVESPEED_API_KEY 필요 (캐릭터 시트·씬 이미지)")

    use_existing = bool(args.sheet_url and args.anchor)
    print("end-to-end 생성 중... (실제 API, 수 분 소요)\n")

    def cb(pct, msg):
        print(f"  {pct:3d}% {msg}")

    result = generate_full(
        "verify-orch",
        SAMPLE_SCRIPT,
        character_spec=None if use_existing else SAMPLE_CHARACTER,
        sheet_url=args.sheet_url,
        anchor=args.anchor,
        voice_id=args.voice_id,
        num_scenes=args.num_scenes,
        progress_cb=cb,
    )

    print("\n" + json.dumps(result, ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    ok = bool(result.get("video_url")) and bool(result.get("thumbnail_url"))
    print(f"  {'✓' if result.get('video_url') else '✗'} video_url: {result.get('video_url')}")
    print(f"  {'✓' if result.get('thumbnail_url') else '✗'} thumbnail_url: {result.get('thumbnail_url')}")
    print(f"  씬 {len(result.get('scenes', []))}개, 타이밍 {len(result.get('scene_timings', []))}개")
    print("=" * 60)
    print(f"결과: {'통과 ✅ — video/thumbnail 열어 최종 확인' if ok else '실패 ✗'}")


if __name__ == "__main__":
    main()
