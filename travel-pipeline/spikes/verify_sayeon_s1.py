"""검증용 throwaway — PR-S1 로컬 검증 (서비스 함수 직접 호출).

샘플 사연 대본(국문)을 넣어 split_script 를 호출하고, 결과 scenes JSON 을 출력한 뒤
자동 점검한다:
  - 씬 개수 6~10 (num_scenes 지정 시 그 수)
  - 씬마다 narration/subtitle 존재 (1:1)
  - subtitle 이 narration 보다 짧음(압축)
  - highlight 가 subtitle 의 부분문자열
  - motion 이 허용 enum
  - image_prompt 에 캐릭터 외모 단어(머리/안경/옷 등)가 없는지 (경고)

OPENAI_API_KEY 만 있으면 동작한다. 프로덕션 미연결(검증 후 삭제 가능).

실행:
  cd travel-pipeline
  export OPENAI_API_KEY=...                 # Windows: set OPENAI_API_KEY=...
  py spikes/verify_sayeon_s1.py
  py spikes/verify_sayeon_s1.py --num-scenes 7
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

from services.sayeon_split import _ALLOWED_MOTIONS, split_script  # noqa: E402

# 짧은 샘플 사연(1인칭 감성 + 반전 + 마지막 후킹 질문).
SAMPLE_SCRIPT = """
스무 살 때, 저는 엄마의 낡은 코트가 부끄러웠어요.
친구들 앞에서 엄마가 그 코트를 입고 오면 모른 척했죠.
어느 날 엄마에게 새 옷을 왜 안 사냐고 짜증을 냈어요.
엄마는 그냥 웃으며 괜찮다고만 했어요.
한참 뒤, 엄마의 서랍에서 낡은 가계부를 발견했어요.
거기엔 제 학원비와 등록금이 빼곡히 적혀 있었어요.
엄마는 당신 옷 한 벌 살 돈을 전부 저에게 쓰고 있었던 거예요.
그제야 저는 그 코트가 부끄러운 게 아니라, 제가 부끄러운 사람이었다는 걸 알았어요.
당신은 부모님의 낡은 옷에 담긴 의미를, 너무 늦게 알아버린 적 없나요?
"""

# image_prompt 에 들어가면 안 되는 외모 단어(영문, 휴리스틱).
APPEARANCE_WORDS = [
    "hair", "glasses", "blonde", "brunette", "ponytail", "bangs",
    "earring", "makeup", "beard", "mustache", "freckle",
    "young woman", "old woman", "young man", "teenage",
]

# 시네마틱화 검증: image_prompt 에 카메라 샷 종류가 들어가는지/다양한지 확인용
SHOT_KEYWORDS = [
    "extreme close-up", "close-up", "closeup", "medium shot", "wide shot",
    "over-the-shoulder", "over the shoulder", "low angle", "high angle",
    "long shot", "establishing shot",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="PR-S1 로컬 검증 (split_script 직접 호출)")
    parser.add_argument("--num-scenes", type=int, default=None, help="씬 개수 강제")
    parser.add_argument("--anchor", default="", help="character_anchor(선택)")
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY 미설정 — 환경변수로 키를 주세요.")

    print("씬 분할 중 (gpt-4o-mini)...\n")
    result = split_script(
        SAMPLE_SCRIPT, num_scenes=args.num_scenes, character_anchor=args.anchor
    )
    scenes = result["scenes"]
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # ── 자동 점검 ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("[자동 점검]")
    ok = True

    n = len(scenes)
    if args.num_scenes:
        cond = n == args.num_scenes
        print(f"  {'✓' if cond else '✗'} 씬 개수 {n} (요청 {args.num_scenes})")
        ok &= cond
    else:
        cond = 8 <= n <= 16
        print(f"  {'✓' if cond else '✗'} 씬 개수 {n} (8~16)")
        ok &= cond

    for s in scenes:
        idx = s["index"]
        nar, sub, hl, ip, mo = (
            s["narration"], s["subtitle"], s["highlight"], s["image_prompt"], s["motion"]
        )
        # 1:1 존재
        if not (nar and sub):
            print(f"  ✗ 씬 {idx}: narration/subtitle 누락")
            ok = False
        # subtitle 압축
        if sub and nar and len(sub) >= len(nar):
            print(f"  ⚠ 씬 {idx}: subtitle 이 narration 보다 짧지 않음 (압축 약함)")
        # highlight ⊂ subtitle
        if hl and hl not in sub:
            print(f"  ✗ 씬 {idx}: highlight '{hl}' 가 subtitle 부분문자열 아님")
            ok = False
        # motion enum
        if mo not in _ALLOWED_MOTIONS:
            print(f"  ✗ 씬 {idx}: motion '{mo}' 허용값 아님")
            ok = False
        # image_prompt 외모 단어
        hits = [w for w in APPEARANCE_WORDS if w in ip.lower()]
        if hits:
            print(f"  ⚠ 씬 {idx}: image_prompt 에 외모 단어 {hits} (S2 시트가 처리해야 함)")
        # 시네마틱: 카메라 샷 키워드 존재
        if not any(k in ip.lower() for k in SHOT_KEYWORDS):
            print(f"  ⚠ 씬 {idx}: image_prompt 에 카메라 샷 표기 없음")

    motions = {s["motion"] for s in scenes}
    print(f"  {'✓' if len(motions) > 1 else '⚠'} motion 다양성: {sorted(motions)}")

    # 시네마틱: 씬마다 샷이 다양한지(매번 같은 샷 반복 금지)
    used_shots = {
        next((k for k in SHOT_KEYWORDS if k in s["image_prompt"].lower()), "—")
        for s in scenes
    }
    print(f"  {'✓' if len(used_shots) > 1 else '⚠'} 카메라 샷 다양성: {sorted(used_shots)}")

    print("=" * 60)
    print(f"결과: {'통과 ✅ — PR-S1 OK' if ok else '실패 ✗ — 위 항목 확인'}")


if __name__ == "__main__":
    main()
