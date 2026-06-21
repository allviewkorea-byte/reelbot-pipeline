"""검증용 CLI — 작업지시서 #1 E단계 (sunoapi.org → R2 → DB).

1회 생성(2곡) → 폴링(SUCCESS) → R2 영구 저장 → music_tracks 기록을 끝까지 돌리고
결과(taskId · audioId · r2_key)를 출력한다. 엔드포인트 노출 없이 가장 단순한 검증.

실행 (로컬, py 사용):
  cd travel-pipeline
  export SUNOAPI_ORG_KEY=...
  # 영구 저장: R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_PUBLIC_BASE_URL
  #           + (권장) R2_MUSIC_BUCKET / R2_MUSIC_PUBLIC_BASE_URL
  # DB 기록: SUPABASE_URL / SUPABASE_SECRET_KEY  (테이블 GRANT 선행 — docs/music_tracks.sql)
  py -m pip install -r requirements.txt        # 미설치 시
  py spikes/verify_music_suno.py               # 기본 테마(cafe_jazz)

  # 커스텀:
  py spikes/verify_music_suno.py --theme-slug lofi_rain --style "lofi hip hop, rainy" \
      --title "Lofi Rain"

확인 포인트:
  - R2 music-masters/{theme_slug}/ 에 mp3 2개
  - music_tracks 에 2행(status=SUCCESS, r2_key 채워짐)
"""

from __future__ import annotations

import argparse
import json
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

from services import music_suno  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="sunoapi.org → R2 → DB 검증")
    ap.add_argument("--theme-slug", default="cafe_jazz")
    ap.add_argument("--title", default="Cafe Jazz")
    ap.add_argument("--style", default="relaxing cafe jazz, warm mellow, soft")
    ap.add_argument("--model", default="V5")
    ap.add_argument("--negative-tags", default="vocals, heavy drums")
    ap.add_argument(
        "--instrumental",
        default="true",
        choices=["true", "false"],
        help="기본 true(연주곡)",
    )
    ap.add_argument("--timeout", type=int, default=music_suno.POLL_TIMEOUT)
    ap.add_argument("--interval", type=int, default=music_suno.POLL_INTERVAL)
    args = ap.parse_args()

    if not music_suno.is_available():
        print("✗ SUNOAPI_ORG_KEY 미설정 — 중단", file=sys.stderr)
        return 1

    theme = {
        "theme_slug": args.theme_slug,
        "instrumental": args.instrumental == "true",
        "model": args.model,
        "style": args.style,
        "title": args.title,
        "negativeTags": args.negative_tags or None,
    }
    print(f"▶ 생성 요청: {theme['theme_slug']} (instrumental={theme['instrumental']})")

    result = music_suno.generate_and_store(
        theme, timeout=args.timeout, interval=args.interval
    )

    print(f"\n✓ taskId={result['task_id']}  곡 {len(result['tracks'])}개")
    for i, rec in enumerate(result["tracks"], 1):
        print(
            f"  [{i}] audioId={rec['audio_id']}  "
            f"r2_key={rec['r2_key']}  dur={rec.get('duration')}"
        )
    print("\n전체 record:")
    print(json.dumps(result["tracks"], ensure_ascii=False, indent=2))

    n = len(result["tracks"])
    if n < 2:
        print(f"\n⚠️ 곡이 {n}개 — 보통 요청당 2곡입니다(확인 필요).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
