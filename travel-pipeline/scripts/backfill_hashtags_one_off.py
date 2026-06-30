"""1회성 스크립트 — 기존 업로드 영상 2건의 description에 해시태그 소급 적용.

대상: Nf-GzLIApuU, qDkKgtFnMi4
사용법:
  cd travel-pipeline
  py scripts/backfill_hashtags_one_off.py --dry-run   # 변경될 내용만 출력
  py scripts/backfill_hashtags_one_off.py              # 실제 YouTube + DB 반영
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import music_meta, music_theme, music_uploads
from services.music_store import _supabase_cfg

import httpx
import logging

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

TARGET_VIDEO_IDS = ["Nf-GzLIApuU", "qDkKgtFnMi4"]


def _find_row_by_video_id(video_id: str) -> dict | None:
    url, key = _supabase_cfg()
    if not (url and key):
        return None
    with httpx.Client(timeout=30.0) as c:
        r = c.get(
            f"{url}/rest/v1/music_uploads",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            params={
                "youtube_video_id": f"eq.{video_id}",
                "select": "slug,mix_id,localizations,viz_spec",
                "limit": "1",
            },
        )
        r.raise_for_status()
        rows = r.json()
    return rows[0] if rows else None


def _patch_hashtags(loc: dict, theme: dict, viz_spec: dict | None) -> tuple[dict, bool]:
    """loc 의 각 언어 description 에 해시태그 합침(idempotent). (patched_loc, changed)."""
    hashtags = loc.get("hashtags") or music_meta.build_hashtags(theme, viz_spec)
    hashtag_line = " ".join(hashtags)
    if not hashtag_line:
        return loc, False
    meta = loc.get("meta") or {}
    changed = False
    for d in meta.values():
        desc = str(d.get("description") or "")
        if hashtag_line not in desc:
            d["description"] = (desc.rstrip() + "\n\n" + hashtag_line).strip()
            changed = True
    if not loc.get("hashtags"):
        loc["hashtags"] = hashtags
    loc["meta"] = meta
    return loc, changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="실제 반영 없이 변경 내용만 출력")
    args = parser.parse_args()

    for vid in TARGET_VIDEO_IDS:
        print(f"\n{'='*60}")
        print(f"video_id: {vid}")
        row = _find_row_by_video_id(vid)
        if not row:
            print(f"  ❌ DB에서 youtube_video_id={vid} 행을 찾을 수 없음")
            continue

        mix_id = row["mix_id"]
        slug = row.get("slug") or ""
        loc = row.get("localizations") or {}
        viz_spec = row.get("viz_spec")
        print(f"  mix_id: {mix_id}")
        print(f"  slug: {slug}")
        print(f"  hashtags 배열: {len(loc.get('hashtags') or [])}개")

        meta = loc.get("meta") or {}
        sample_lang = list(meta.keys())[0] if meta else None
        if sample_lang:
            sample_desc = str(meta[sample_lang].get("description") or "")
            has_ht = bool(loc.get("hashtags")) and " ".join(loc["hashtags"]) in sample_desc
            print(f"  {sample_lang} description 해시태그 포함: {has_ht}")

        theme = music_theme.get_theme(slug) or {"slug": slug}
        patched_loc, changed = _patch_hashtags(loc, theme, viz_spec)

        if not changed:
            print("  ✅ 이미 해시태그 포함됨 — 스킵")
            continue

        print(f"  🔧 {len(meta)}개 언어 description에 해시태그 추가 예정")
        if sample_lang:
            patched_desc = patched_loc["meta"][sample_lang]["description"]
            print(f"  --- {sample_lang} description 끝 200자 ---")
            print(f"  {patched_desc[-200:]}")

        if args.dry_run:
            print("  [DRY-RUN] 실제 반영 안 함")
            continue

        # 1) YouTube videos.update (다국어 title/description 갱신, title은 기존 snippet 보존)
        from services.youtube_upload import set_localizations
        src_lang = patched_loc.get("source_lang", "ko")
        yt_result = set_localizations(vid, patched_loc["meta"], default_lang=src_lang)
        if yt_result.get("ok"):
            print(f"  ✅ YouTube localizations 갱신 완료")
        else:
            print(f"  ❌ YouTube 갱신 실패: {yt_result.get('error')}")
            continue

        # 2) DB 캐시도 보정 저장
        db_result = music_uploads.set_localizations(mix_id, patched_loc)
        if db_result.get("stored"):
            print(f"  ✅ DB 캐시 갱신 완료")
        else:
            print(f"  ⚠️ DB 캐시 갱신 실패(YouTube는 반영됨): {db_result.get('error')}")

    print(f"\n{'='*60}")
    print("완료.")


if __name__ == "__main__":
    main()
