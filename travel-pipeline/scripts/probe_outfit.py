"""1회성 스크립트 — 착장 1장 실호출 확인 (A1). 약 $0.011~0.033 + Claude 기획·검수 토큰.

캐릭터의 확정 기준 이미지(01_face·02_body·hair_*) + 로컬 상품 사진 1~4장으로 착장 1장을 만든다.
실제 서비스 흐름(insta_outfit.start → run)을 그대로 타므로 R2·Supabase(ig_outfits)에 저장되고
/insta/outfit 최근 착장 목록에도 보인다.
사용법(WAVESPEED_API_KEY·ANTHROPIC_API_KEY·SUPABASE·R2 필요, docs/ig_outfits.sql 선행):
  cd travel-pipeline
  py scripts/probe_outfit.py 상의.jpg:top 바지.jpg:bottoms 신발.jpg:shoes
"""

from __future__ import annotations

import json
import logging
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from services import insta_outfit as io  # noqa: E402


def main(argv: list[str]) -> None:
    if not argv:
        sys.exit(__doc__)
    batch = secrets.token_hex(4)
    products = []
    for n, arg in enumerate(argv[: io.MAX_PRODUCTS]):
        path, _, kind = arg.partition(":")
        p = io.save_product(batch, n, Path(path).read_bytes(), Path(path).name)
        p["kind"] = kind or p.get("kind")
        print(f"상품 {n}: {p['kind']} · {p.get('desc')} · {p['url']}")
        products.append(p)
    job = io.start("chaei", products)
    print("작업:", job["id"], job["outfit_id"])
    io.run(job["id"])
    row = io.view(io.get_outfit(job["outfit_id"]))
    print(json.dumps({k: row.get(k) for k in ("status", "attempts", "cost_usd", "plan", "review", "processed_url",
                                              "image_url", "prompt", "refs")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
