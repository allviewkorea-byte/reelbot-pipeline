"""검증용 throwaway — PR-S3 로컬 검증 (서비스 함수 직접 호출).

샘플 narration 3~4줄 → 라인별 TTS + 합친 나레이션(.wav) + scene_timings 출력·로컬 저장.
SUPERTONE_API_KEY(+voice_id) 있으면 Supertone, 없으면 Edge TTS 폴백.
ffmpeg/ffprobe 가 PATH 에 있어야 한다. 프로덕션 미연결(검증 후 삭제 가능).

실행:
  cd travel-pipeline
  # (선택) export SUPERTONE_API_KEY=...  SUPERTONE_VOICE_ID=...   # 없으면 Edge TTS
  py -m pip install -r requirements.txt
  py spikes/verify_sayeon_s3.py
  py spikes/verify_sayeon_s3.py --voice-id <supertone_voice_id> --gap 0.5

점검:
  - 라인별 TTS 생성 + concat 성공(narration.wav)
  - scene_timings 가 연속(다음 start == 이전 end)이고 [0, total] 을 덮는가
  - 전환 경계가 라인 사이 쉼 중앙인가(인접 구간 사이 간격 == gap)
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

from services.sayeon_tts import generate_tts  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "output" / "verify_s3"

# 샘플 narration(국문) — S1 출력 형식과 동일 ({index, narration}).
SAMPLE_SCENES = [
    {"index": 1, "narration": "스무 살 때, 저는 엄마의 낡은 코트가 부끄러웠어요."},
    {"index": 2, "narration": "친구들 앞에서 엄마가 그 코트를 입고 오면 모른 척했죠."},
    {"index": 3, "narration": "한참 뒤, 엄마의 서랍에서 낡은 가계부를 발견했어요."},
    {"index": 4, "narration": "당신은 부모님의 낡은 옷에 담긴 의미를 너무 늦게 알아버린 적 없나요?"},
]


def main() -> None:
    parser = argparse.ArgumentParser(description="PR-S3 로컬 검증 (generate_tts 직접 호출)")
    parser.add_argument("--voice-id", default=None, help="Supertone voice_id(선택)")
    parser.add_argument("--gap", type=float, default=0.4, help="라인 사이 쉼(초)")
    args = parser.parse_args()

    provider = "Supertone" if (os.getenv("SUPERTONE_API_KEY") and (args.voice_id or os.getenv("SUPERTONE_VOICE_ID"))) else "Edge TTS(폴백)"
    print(f"TTS 공급자: {provider}\nTTS 생성 중...\n")

    result = generate_tts(
        "verify-s3",
        SAMPLE_SCENES,
        voice_id=args.voice_id,
        gap_sec=args.gap,
        output_dir=str(OUT_DIR),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    timings = result["scene_timings"]
    total = result["total_duration"]

    print("\n" + "=" * 60)
    print(f"[자동 점검]  공급자={result['voice']}  total={total}s  오디오={result['audio_url']}")
    ok = True

    if abs(timings[0]["start"]) > 1e-6:
        print(f"  ✗ 첫 씬 start 가 0 이 아님: {timings[0]['start']}"); ok = False
    if abs(timings[-1]["end"] - total) > 0.05:
        print(f"  ✗ 마지막 씬 end({timings[-1]['end']}) != total({total})"); ok = False

    # 연속성: 다음 start == 이전 end
    for a, b in zip(timings, timings[1:]):
        if abs(b["start"] - a["end"]) > 1e-3:
            print(f"  ✗ 씬 {a['index']}→{b['index']} 불연속: {a['end']} vs {b['start']}")
            ok = False

    # duration 합 == total
    dsum = round(sum(t["duration"] for t in timings), 2)
    if abs(dsum - round(total, 2)) > 0.1:
        print(f"  ✗ duration 합({dsum}) != total({round(total,2)})"); ok = False

    print(f"  로컬 저장: {OUT_DIR}/narration.wav (+ line_*.wav)")
    print("=" * 60)
    print(f"결과: {'통과 ✅ — PR-S3 OK' if ok else '실패 ✗ — 위 항목 확인'}")
    print("→ narration.wav 를 직접 들어보고 음질/싱크를 확인하세요.")


if __name__ == "__main__":
    main()
