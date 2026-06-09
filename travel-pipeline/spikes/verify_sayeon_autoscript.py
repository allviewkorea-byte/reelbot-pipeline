"""검증용 throwaway — 자동 사연 생성 점검.

generate_script 를 여러 번 호출해 1인칭·줄수(6~9)·마무리 질문·다양성을 확인한다.
OPENAI_API_KEY 필요. 프로덕션 미연결.

실행:
  cd travel-pipeline
  export OPENAI_API_KEY=...
  py spikes/verify_sayeon_autoscript.py
  py spikes/verify_sayeon_autoscript.py --runs 3 --gender woman --age "early 20s"
"""

from __future__ import annotations

import argparse
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

from services.sayeon_autoscript import generate_script  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="자동 사연 생성 검증")
    parser.add_argument("--runs", type=int, default=2, help="반복 횟수(다양성 확인)")
    parser.add_argument("--topic", default="", help="고정 주제(없으면 랜덤)")
    parser.add_argument("--gender", default="woman")
    parser.add_argument("--age", default="early 20s")
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY 필요")

    character = {"gender": args.gender, "age": args.age}
    firsts: list[str] = []
    ok = True
    for r in range(1, args.runs + 1):
        res = generate_script(topic=args.topic, character=character)
        script = res["script"]
        lines = [ln for ln in script.splitlines() if ln.strip()]
        print(f"\n── run {r}  [주제: {res['topic']}]  제목: {res['title']}")
        print(script)
        # 점검
        n = len(lines)
        if not (6 <= n <= 9):
            print(f"  ⚠ 줄수 {n} (6~9 권장)")
        first_person = any(t in script for t in ("나", "내", "제", "저"))
        print(f"  {'✓' if first_person else '✗'} 1인칭 표현")
        ok &= first_person
        ends_q = lines[-1].rstrip().endswith("?") if lines else False
        print(f"  {'✓' if ends_q else '⚠'} 마무리 질문")
        firsts.append(lines[0] if lines else "")

    if args.runs > 1:
        diverse = len(set(firsts)) == len(firsts)
        print(f"\n{'✓' if diverse else '⚠'} 첫 줄 다양성: {len(set(firsts))}/{len(firsts)}")

    print("\n" + ("통과 ✅" if ok else "실패 ✗ — 위 항목 확인"))


if __name__ == "__main__":
    main()
