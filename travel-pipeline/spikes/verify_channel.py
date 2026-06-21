"""검증용 CLI — 작업지시서 #5 (주제 → 음원 연결 + instrumental 라우팅).

주제 1개를 뽑거나 불러와 음원 믹스 1개까지 연결한다(run_theme). type 에 따라
연주/보컬 경로가 자동 분기됨을 확인한다.

모드:
  --dry          : 주제만 생성·표시 + 어느 경로(연주/보컬) 타는지 출력. 곡 생성 0(크레딧 0).
  --auto-theme   : generate_theme() → produce (⚠️ 실곡 생성, Suno 크레딧 소모).
  --theme-slug X : music_themes 에서 기존 주제 불러와 produce (⚠️ 크레딧 소모).
  --n / --minutes: 곡수·믹스 길이 override.

실행 (로컬, py 사용):
  cd travel-pipeline
  export ANTHROPIC_API_KEY=...                # 주제(+보컬 가사)
  # SUPABASE_*(주제 조회/기록), R2_*/SUNOAPI_*(--auto-theme/--theme-slug 곡 생성)
  py spikes/verify_channel.py --dry                       # 무크레딧 연결 점검
  py spikes/verify_channel.py --auto-theme --n 3 --minutes 8
  py spikes/verify_channel.py --theme-slug rainy_piano --minutes 8
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

from services import music_produce, music_theme  # noqa: E402


def _route_line(theme: dict, n: int) -> str:
    t = (theme.get("type") or "vocal").strip().lower()
    if t == "instrumental":
        return f"→ [instrumental] 경로: 가사 스킵, style_prompt 로 {n}곡 → 마스터 → 믹스 예정"
    return f"→ [vocal] 경로: 가사(Sonnet, lyric_tone 반영) {n}곡 → 보컬곡 → 마스터 → 믹스 예정"


def main() -> int:
    ap = argparse.ArgumentParser(description="주제 → 음원 연결 검증")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry", action="store_true", help="주제만, 곡 생성 안 함(크레딧 0)")
    mode.add_argument("--auto-theme", action="store_true", help="generate_theme → produce(실곡)")
    ap.add_argument("--theme-slug", default="", help="기존 주제 slug 로 produce")
    ap.add_argument("--n", type=int, default=0, help="곡수 override(0=주제 track_count)")
    ap.add_argument("--minutes", type=float, default=8.0)
    args = ap.parse_args()

    if not music_theme.is_available():
        print("✗ ANTHROPIC_API_KEY 미설정 — 주제 생성 불가", file=sys.stderr)
        return 1

    # 주제 확보: --theme-slug 우선 로드, 아니면 생성.
    if args.theme_slug:
        theme = music_theme.get_theme(args.theme_slug)
        if not theme:
            print(f"✗ 주제를 찾을 수 없음: {args.theme_slug}", file=sys.stderr)
            return 1
    else:
        # --dry 는 저장 안 함, --auto-theme 는 저장.
        theme = music_theme.generate_theme(persist=args.auto_theme)

    n = args.n or int(theme.get("track_count") or 3)
    print("뽑힌 주제:")
    print(json.dumps(theme, ensure_ascii=False, indent=2))
    print(f"\n{_route_line(theme, n)}")

    if args.dry or (not args.auto_theme and not args.theme_slug):
        print("\n✓ --dry — 연결 로직만 점검(곡 생성 0). 경로 확인 완료.")
        return 0

    # 실곡 생성(크레딧 소모).
    print(f"\n▶ 음원 생성 시작(type={theme.get('type')}, n={n})...")
    result = music_produce.run_theme(
        theme=theme, n=n, minutes=args.minutes, progress=lambda m: print(f"  · {m}")
    )
    mix = result.get("mix") or {}
    res = result.get("result") or {}
    print(f"\n✓ track_type={res.get('track_type')} 트랙 {len(res.get('produced', []))}개")
    if mix:
        print(f"✓ mix_id={mix['mix_id']} 곡={mix['track_count']} 길이={mix['total_duration']}s")
        print(f"  mp3 : {mix['mp3_url']}")
        print(f"  json: {mix['json_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
