"""검증용 CLI — 작업지시서 #7 (음악 채널 유튜브 업로드).

기존 음원(slug+mix_id)으로 영상 생성 + 음악 채널(Revezen) 비공개 업로드 테스트.
--dry 면 업로드 직전까지만(YouTube API 호출 0) — 메타데이터 구성·경로만 점검.

실행 (로컬, py 사용):
  cd travel-pipeline
  export OPENAI_API_KEY=...   # 배경 이미지
  # R2_*/SUPABASE_* — 믹스/영상 저장
  # 업로드 시: YOUTUBE_CLIENT_ID/SECRET + YOUTUBE_CHANNEL_ID_MUSIC + (인증된)REFRESH_TOKEN_MUSIC
  py spikes/verify_upload.py --theme-slug rainy_piano --mix-id mix_2026... --dry
  py spikes/verify_upload.py --theme-slug rainy_piano --seconds 25   # 실제 업로드(크레딧/API)
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
from services.youtube_upload import build_music_metadata, upload_music_video  # noqa: E402


def _load_mix(slug: str, mix_id: str) -> dict:
    tmp_json = Path(tempfile.gettempdir()) / f"{slug}_{mix_id}.json"
    r2_storage.download_music_object(r2_storage.music_mix_key(slug, mix_id, "json"), str(tmp_json))
    meta = json.loads(tmp_json.read_text(encoding="utf-8"))
    return {
        "mix_id": mix_id,
        "mp3_url": r2_storage.music_mix_url(slug, mix_id, "mp3"),
        "tracks": meta.get("tracks") or [],
        "total_duration": meta.get("total_duration"),
        "theme_slug": slug,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="음악 유튜브 업로드 검증")
    ap.add_argument("--theme-slug", required=True)
    ap.add_argument("--mix-id", default="")
    ap.add_argument("--seconds", type=float, default=25.0, help="영상 테스트 컷(0=전체)")
    ap.add_argument("--dry", action="store_true", help="업로드 직전까지만(API 0)")
    args = ap.parse_args()

    if not r2_storage.is_available():
        print("✗ R2 미설정 — 믹스 조회 불가", file=sys.stderr)
        return 1

    slug = args.theme_slug
    theme = music_theme.get_theme(slug) or {"slug": slug, "title_kr": slug}
    mix_id = args.mix_id or r2_storage.latest_mix_id(slug)
    if not mix_id:
        print(f"✗ 믹스 없음(music-mixes/{slug}/)", file=sys.stderr)
        return 1
    mix = _load_mix(slug, mix_id)
    print(f"▶ slug={slug} mix_id={mix_id} 곡={len(mix['tracks'])}")

    # 업로드 메타데이터 미리보기(항상 출력).
    title, description, tags = build_music_metadata(theme, mix)
    print("\n=== 업로드 메타데이터 ===")
    print(f"제목 : {title}")
    print(f"태그 : {tags}")
    print(f"설명 :\n{description}")
    print("카테고리: 10(음악)  privacy: private(비공개)")

    if args.dry:
        print("\n✓ --dry — 업로드 직전까지만(YouTube API 호출 0). 메타데이터 점검 완료.")
        return 0

    # 영상 생성 → 업로드.
    print("\n▶ 영상 생성...")
    vres = music_video.make_video(theme, mix, seconds=(None if args.seconds == 0 else args.seconds))
    print(f"  mp4: {vres['video_url']}")
    print("▶ 음악 채널 업로드(비공개)...")
    up = upload_music_video(vres["video_url"], theme, mix)
    print(f"\n✓ 업로드 완료: {up['video_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
