"""검증용 CLI — 작업지시서 #3 (가사 자동생성 + 다곡 오케스트레이션).

⭐ --lyrics-only : 가사만 생성·출력(곡 생성 안 함, 크레딧 0) → 대표 검수용. 품질 바를
   넘는 게 확인된 뒤에야 --full 로 대량 자동화한다.
   --full       : 소량(기본 3곡)으로 가사→보컬→마스터→믹스 end-to-end. 풀은 --n 12.

가사 모델은 기본 CLAUDE_MODEL(Haiku), env MUSIC_LYRICS_MODEL 로 교체(검수 시 sonnet-4-6 비교):
   MUSIC_LYRICS_MODEL=claude-sonnet-4-6 py spikes/verify_music_produce.py --lyrics-only --n 12

실행 (로컬, py 사용):
  cd travel-pipeline
  export ANTHROPIC_API_KEY=...           # 가사(필수)
  export SUNOAPI_ORG_KEY=...             # --full 시 곡 생성
  # R2_* / SUPABASE_* 기존 자격증명(--full 마스터·믹스·DB)
  py -m pip install -r requirements.txt  # 미설치 시

  py spikes/verify_music_produce.py --lyrics-only --theme-slug citypop --n 12
  py spikes/verify_music_produce.py --full --theme-slug citypop --n 3 --minutes 8

확인 포인트:
  - lyrics-only: 12곡 가사 출력 → 깊이·여운·다양성·클리셰 검수
  - full: R2 music-masters/{theme}/mastered/ + music-mixes/{theme}/{mix_id}.mp3
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

from services import music_lyrics, music_produce  # noqa: E402


def _print_song(i: int, s: dict) -> None:
    sc = s.get("scores") or {}
    sc_str = " ".join(f"{k}={sc[k]}" for k in ("depth", "resonance", "monotony", "cliche") if k in sc)
    print(f"\n{'='*70}\n[{i}] {s.get('title')}  ({s.get('sub_theme')})")
    print(f"  핵심 메시지: {s.get('core_message')}")
    if sc_str:
        print(f"  자기검토: {sc_str}  revised={s.get('revised')}")
    if s.get("issues"):
        print(f"  지적: {s.get('issues')}")
    print(f"  vocalGender: {s.get('vocalGender')}  style: {s.get('style')}")
    print(f"{'-'*70}\n{s.get('lyrics')}")


def main() -> int:
    ap = argparse.ArgumentParser(description="가사 생성 + 다곡 오케스트레이션 검증")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--lyrics-only", action="store_true", help="가사만(크레딧 0, 검수용)")
    mode.add_argument("--full", action="store_true", help="가사→곡→마스터→믹스 e2e")
    ap.add_argument("--theme-slug", default="citypop")
    ap.add_argument("--genre-theme", default="city pop")
    ap.add_argument("--n", type=int, default=3, help="곡 수(가사 수)")
    ap.add_argument("--minutes", type=float, default=8.0, help="믹스 목표 길이(분, --full)")
    ap.add_argument("--language", default="ko")
    ap.add_argument("--save", default="", help="가사 JSON 저장 경로(선택)")
    args = ap.parse_args()

    # 기본은 검수 우선(--lyrics-only). --full 을 명시해야 곡 생성.
    lyrics_only = args.lyrics_only or not args.full

    if not music_lyrics.is_available():
        print("✗ ANTHROPIC_API_KEY 미설정 — 가사 생성 불가", file=sys.stderr)
        return 1
    print(f"▶ 가사 모델: {os.getenv('MUSIC_LYRICS_MODEL') or 'claude-haiku-4-5-20251001'} | 주제: {args.genre_theme} | {args.n}곡")

    songs = music_lyrics.generate_lyrics(
        args.genre_theme, args.n, language=args.language, progress=lambda m: print(f"  · {m}")
    )
    for i, s in enumerate(songs, 1):
        _print_song(i, s)

    if args.save:
        Path(args.save).write_text(json.dumps(songs, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n💾 가사 저장: {args.save}")

    if lyrics_only:
        print(f"\n✓ lyrics-only — {len(songs)}곡 가사 출력 완료(곡 생성 안 함). 검수 후 --full 진행.")
        return 0

    # --full: 이미 만든 가사로 곡→마스터→믹스(가사 재생성 방지 위해 songs 전달).
    print(f"\n▶ [full] {len(songs)}곡 보컬 생성 → 마스터 → 믹스...")
    result = music_produce.produce(
        args.theme_slug,
        genre_theme=args.genre_theme,
        language=args.language,
        minutes=args.minutes,
        lyrics=songs,
    )
    mix = result.get("mix") or {}
    print(f"\n✓ 보컬 트랙 {len(result['produced'])}개 / 마스터 {len(result['mastered'])}개")
    if mix:
        print(f"✓ mix_id={mix['mix_id']} 곡={mix['track_count']} 길이={mix['total_duration']}s")
        print(f"  mp3 : {mix['mp3_url']}")
        print(f"  json: {mix['json_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
