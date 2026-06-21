"""검증용 CLI — 작업지시서 #6 (영상화 1차: 배경 + 비주얼라이저 + 곡 제목).

기존 믹스 slug 로 영상만 생성한다(음원 재생산 없음). 배경(gpt-image-1) +
Ken Burns + 비주얼라이저 + 주제/곡 제목 → 1920x1080 mp4.

실행 (로컬, py 사용):
  cd travel-pipeline
  export OPENAI_API_KEY=...      # 배경 이미지(gpt-image-1)
  # R2_*/SUPABASE_* — 믹스 조회·배경/mp4 저장
  py -m pip install -r requirements.txt

  # 짧은 테스트 컷(앞 25초)로 합성 점검:
  py spikes/verify_video.py --theme-slug rainy_piano --seconds 25
  # 특정 믹스 지정:
  py spikes/verify_video.py --theme-slug rainy_piano --mix-id mix_20260621_140000

확인 포인트:
  - mp4 1920x1080 H.264, 오디오 싱크
  - 비주얼라이저가 음악에 반응 + 배경 미세 모션 + 주제/곡 제목 표시
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: BLE001
    pass

from adapters import r2_storage  # noqa: E402
from services import music_theme, music_video  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="음악 영상화 검증(영상만)")
    ap.add_argument("--theme-slug", required=True)
    ap.add_argument("--mix-id", default="", help="미지정 시 해당 slug 최신 믹스")
    ap.add_argument("--seconds", type=float, default=25.0, help="짧은 테스트 컷 길이(0=전체)")
    ap.add_argument("--viz", default="", choices=["", "showwaves", "showcqt", "showspectrum"])
    args = ap.parse_args()

    if not r2_storage.is_available():
        print("✗ R2 미설정 — 믹스 조회/저장 불가", file=sys.stderr)
        return 1

    slug = args.theme_slug
    # 주제(배경 프롬프트용). DB 에 없으면 slug 만으로 최소 진행.
    theme = music_theme.get_theme(slug) or {"slug": slug, "title_kr": slug}

    # 믹스 확보: --mix-id 우선, 아니면 최신.
    mix_id = args.mix_id or r2_storage.latest_mix_id(slug)
    if not mix_id:
        print(f"✗ 믹스를 찾을 수 없음(music-mixes/{slug}/). 먼저 음원을 만드세요.", file=sys.stderr)
        return 1

    # 믹스 오프셋 JSON 다운로드 → tracks/total_duration 확보(크로스플랫폼 임시경로).
    tmp_json = Path(tempfile.gettempdir()) / f"{slug}_{mix_id}.json"
    r2_storage.download_music_object(
        r2_storage.music_mix_key(slug, mix_id, "json"), str(tmp_json)
    )
    meta = json.loads(tmp_json.read_text(encoding="utf-8"))
    mix = {
        "mix_id": mix_id,
        "mp3_url": r2_storage.music_mix_url(slug, mix_id, "mp3"),
        "tracks": meta.get("tracks") or [],
        "total_duration": meta.get("total_duration"),
        "theme_slug": slug,
    }
    print(f"▶ slug={slug} mix_id={mix_id} 곡={len(mix['tracks'])} 길이={mix['total_duration']}s")
    print(f"  컷={'전체' if args.seconds == 0 else str(args.seconds)+'초'} viz={args.viz or 'showwaves'}")

    result = music_video.make_video(
        theme, mix, seconds=(None if args.seconds == 0 else args.seconds), viz=(args.viz or None)
    )
    print(f"\n✓ video_id={result['video_id']} 길이={result['duration']}s")
    print(f"  mp4: {result['video_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
