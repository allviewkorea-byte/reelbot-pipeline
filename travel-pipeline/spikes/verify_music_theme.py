"""검증용 CLI — 작업지시서 #4 (주제 생성기).

주제 헌법(prompts/music_themes.md)으로 새 주제 N개를 뽑아 보기 좋게 출력한다.
곡 생성·Suno 크레딧 0 — Haiku 호출만(영상당 ~$0.002). 대표가 "랜덤 주제가
다양하고 말 되는지" 눈으로 검수하는 용도.

실행 (로컬, py 사용):
  cd travel-pipeline
  export ANTHROPIC_API_KEY=...          # 주제 생성(필수)
  # (선택) SUPABASE_URL / SUPABASE_SECRET_KEY — 없으면 dedup 은 메모리 누적분만
  py -m pip install -r requirements.txt # 미설치 시

  py spikes/verify_music_theme.py --n 5 --dry-run     # DB 저장 안 함(검수용)
  MUSIC_THEME_MODEL=claude-haiku-4-5-20251001 py spikes/verify_music_theme.py --n 5 --dry-run

확인 포인트:
  - 5개가 서로 다른 장르·상황으로 나오는가
  - 코히어런스 위반(수면 EDM, 운동 앰비언트 등)이 없는가
  - instrumental 은 lyric_tone=null, vocal 은 lyric_tone 채워짐
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

from services import music_theme  # noqa: E402


def _print_theme(i: int, t: dict) -> None:
    print(f"\n{'='*70}\n[{i}] {t.get('slug')}   ({t.get('type')})")
    print(f"  제목  : {t.get('title_kr')}")
    print(f"  장르  : {t.get('genre')}   상황: {t.get('situation')}   무드: {t.get('mood')}")
    print(f"  style : {t.get('style_prompt')}")
    print(f"  가사톤: {t.get('lyric_tone')}   곡수: {t.get('track_count')}")


def main() -> int:
    ap = argparse.ArgumentParser(description="주제 생성기 검증(곡 생성 없음)")
    ap.add_argument("--n", type=int, default=5, help="생성 개수")
    ap.add_argument("--dry-run", action="store_true", help="DB 저장 안 함(dedup 은 메모리)")
    ap.add_argument("--avoid-recent", type=int, default=10)
    args = ap.parse_args()

    if not music_theme.is_available():
        print("✗ ANTHROPIC_API_KEY 미설정 — 주제 생성 불가", file=sys.stderr)
        return 1
    model = os.getenv("MUSIC_THEME_MODEL") or "claude-haiku-4-5-20251001"
    print(f"▶ 주제 모델: {model} | {args.n}개 생성 | dry-run={args.dry_run}")

    seen: list[dict] = []  # 같은 실행 내 dedup(장르·slug 분산)
    genres: list[str] = []
    for i in range(1, args.n + 1):
        try:
            t = music_theme.generate_theme(
                avoid_recent=args.avoid_recent,
                persist=not args.dry_run,
                extra_recent=seen,
            )
        except Exception as e:  # noqa: BLE001
            print(f"✗ {i}번째 생성 실패: {e}", file=sys.stderr)
            continue
        _print_theme(i, t)
        seen.append({"slug": t.get("slug"), "genre": t.get("genre"), "situation": t.get("situation")})
        genres.append(str(t.get("genre")))

    uniq = len(set(genres))
    print(f"\n{'='*70}\n✓ {len(seen)}개 생성 | 고유 장르 {uniq}/{len(genres)}"
          + ("" if uniq == len(genres) else "  ⚠️ 장르 중복 있음(헌법 5번 점검)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
