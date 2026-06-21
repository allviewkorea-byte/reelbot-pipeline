"""검증용 CLI — 작업지시서 #2 (보컬 입력 + 마스터링 + 롱폼 믹스).

두 가지 검증을 한 스크립트로 돌린다(인자로 선택):
  (1) vocal   : 가사 1개로 보컬 곡 생성 → R2 저장 확인 (A 검증)
  (2) pipeline: 한 테마 트랙들(기존 R2/DB 재활용) → 마스터 → 믹스 → R2 롱폼 mp3 + JSON

⚠️ 크레딧 절약: pipeline 은 기본적으로 **생성 없이** music_tracks 의 기존 곡을
재활용한다(#1 의 cafe_jazz 등). 짧은 믹스(--minutes 10)로 배관부터 확인하고,
풀 길이는 --minutes 45 처럼 늘린다. 보컬 생성은 --mode vocal/both 일 때만.

실행 (로컬, py 사용):
  cd travel-pipeline
  export SUNOAPI_ORG_KEY=...     # vocal 모드만 필요
  # R2_* / SUPABASE_* 기존 자격증명(마스터·믹스·조회)
  py -m pip install -r requirements.txt   # 미설치 시

  # 마스터+믹스만(생성 없음, 기존 cafe_jazz 재활용, 짧은 믹스):
  py spikes/verify_music_pipeline.py --mode pipeline --theme-slug cafe_jazz --minutes 10

  # 보컬 스모크(가사 파일 또는 인라인):
  py spikes/verify_music_pipeline.py --mode vocal --theme-slug citypop_love \
      --lyrics @lyrics.txt --vocal-gender female --style "city pop, 80s, warm"

확인 포인트:
  - vocal: R2 music-masters/{theme}/ 에 보컬 mp3 저장
  - pipeline: music-masters/{theme}/mastered/ 마스터본 + music-mixes/{theme}/{mix_id}.{mp3,json}
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# travel-pipeline 패키지 루트를 import 경로에 추가(spikes/ 아래 실행 대비).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: BLE001
    pass

from adapters import r2_storage  # noqa: E402
from services import music_master, music_mix, music_store, music_suno  # noqa: E402


def _read_lyrics(arg: str) -> str:
    """--lyrics 값. '@경로'면 파일에서 읽고, 아니면 그대로 가사로 본다."""
    if arg.startswith("@"):
        return Path(arg[1:]).read_text(encoding="utf-8").strip()
    return arg.strip()


def _do_vocal(args) -> int:
    if not music_suno.is_available():
        print("✗ SUNOAPI_ORG_KEY 미설정 — vocal 생성 불가", file=sys.stderr)
        return 1
    if not args.lyrics:
        print("✗ --lyrics 가 필요합니다(보컬 곡 가사).", file=sys.stderr)
        return 1
    lyrics = _read_lyrics(args.lyrics)
    theme = {
        "theme_slug": args.theme_slug,
        "instrumental": False,
        "style": args.style or "pop, warm vocals",
        "title": args.title or args.theme_slug,
        "lyrics": lyrics,
    }
    if args.vocal_gender:
        theme["vocalGender"] = args.vocal_gender
    print(f"▶ [vocal] 생성: {args.theme_slug} (가사 {len(lyrics)}자)")
    result = music_suno.generate_and_store(theme, timeout=args.timeout)
    print(f"✓ taskId={result['task_id']} 곡 {len(result['tracks'])}개")
    for i, rec in enumerate(result["tracks"], 1):
        print(f"  [{i}] audioId={rec['audio_id']} r2_key={rec['r2_key']}")
    return 0


def _do_pipeline(args) -> int:
    theme = args.theme_slug
    rows = music_store.list_tracks(theme)
    print(f"▶ [pipeline] {theme} — music_tracks 조회: {len(rows)}곡")
    if not rows:
        print(
            "✗ 곡이 없습니다 — 먼저 #1(verify_music_suno.py)로 생성하거나 --mode both 사용.",
            file=sys.stderr,
        )
        return 1

    # 1) 마스터링(멱등) — 이미 있으면 스킵.
    print("· 마스터링(2-pass loudnorm -14 LUFS)...")
    mastered = music_master.master_theme(theme, rows)
    done = sum(1 for m in mastered if m.get("mastered_key"))
    skipped = sum(1 for m in mastered if m.get("skipped"))
    print(f"  마스터본 {done}개(스킵 {skipped})")

    # 2) 롱폼 믹스.
    print(f"· 믹스(목표 {args.minutes}분, 크로스페이드 {args.crossfade}s)...")
    mix = music_mix.build_mix(
        theme, rows, minutes=args.minutes, crossfade=args.crossfade, seed=args.seed
    )
    print(f"✓ mix_id={mix['mix_id']} 곡={mix['track_count']} 길이={mix['total_duration']}s")
    print(f"  mp3 : {mix['mp3_url']}")
    print(f"  json: {mix['json_url']}")
    print("  오프셋:")
    for t in mix["tracks"]:
        print(f"    #{t['order']} {t['start_sec']:>7.1f}s  {t['title']} ({t['audio_id']})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="음악 보컬+마스터+믹스 검증")
    ap.add_argument("--mode", choices=["vocal", "pipeline", "both"], default="pipeline")
    ap.add_argument("--theme-slug", default="cafe_jazz")
    ap.add_argument("--lyrics", default="", help="보컬 가사. '@경로'면 파일에서 읽음")
    ap.add_argument("--style", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--vocal-gender", default="", choices=["", "male", "female"])
    ap.add_argument("--minutes", type=float, default=10.0, help="믹스 목표 길이(분)")
    ap.add_argument("--crossfade", type=float, default=music_mix.CROSSFADE_SEC)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--timeout", type=int, default=music_suno.POLL_TIMEOUT)
    args = ap.parse_args()

    if not r2_storage.is_available():
        print("⚠️ R2 미설정 — 영구 저장 불가(검증 의미 없음). R2_* 설정 필요.", file=sys.stderr)

    rc = 0
    if args.mode in ("vocal", "both"):
        rc = _do_vocal(args) or rc
    if args.mode in ("pipeline", "both"):
        rc = _do_pipeline(args) or rc
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
