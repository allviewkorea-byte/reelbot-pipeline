"""1회성 스크립트 — 내 상품으로 코디 실호출 확인 (A2-3a). 약 $0.05~0.1(쿠팡 픽 비전 + 착장 1~3회 + 검수).

보세 상품 사진 1장(+링크) → 빈 종류를 AI 가 정하고 쿠팡에서 골라 → 착장 1장.
실제 서비스 흐름(insta_coordi.start → run)을 그대로 타므로 R2·Supabase(ig_products·ig_looks·ig_outfits)에 저장되고
/insta/outfit 최근 착장 목록에도 보인다. 끝나면 쿠팡 이미지 사본이 지워졌는지도 확인한다.
사용법(WAVESPEED·ANTHROPIC·COUPANG_PARTNERS 키·SUPABASE·R2 필요, docs/ig_coordi.sql 선행):
  cd travel-pipeline
  py scripts/probe_coordi.py 니트.jpg:top https://www.musinsa.com/products/123
  (모드를 바꾸려면 끝에 only — 쿠팡 없이 넣은 상품만)
"""

from __future__ import annotations

import json
import logging
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

from services import insta_coordi as C  # noqa: E402
from services import insta_outfit as io  # noqa: E402
from services import insta_picks as K  # noqa: E402


def main(argv: list[str]) -> None:
    if not argv:
        sys.exit(__doc__)
    mode = "only" if argv[-1] == "only" else "fill"
    path, _, kind = argv[0].partition(":")
    link = next((a for a in argv[1:] if a.startswith("https://")), None)
    p = io.save_product(secrets.token_hex(4), 0, Path(path).read_bytes(), Path(path).name)
    p["kind"] = kind or p.get("kind")
    print(f"보세 상품: {p['kind']} · {p.get('desc')} · {p['url']} · 링크 {link or '-'}")
    d = K.Deps()
    job = C.start("chaei", [{**p, "link": link}], mode, d=d)
    print("작업:", job["id"], job["look_id"], "모드", mode)
    C.run(job["id"])
    j = C.get_job(job["id"])
    print("결과:", j["state"], j.get("error") or "", "비용", j.get("cost"))
    look = d.rest("ig_looks", "GET", params={"select": "*", "id": f"eq.{job['look_id']}"})[0]
    for it in look.get("items") or []:
        c = it.get("pick") or {}
        print(f"  {it['kind']:<9} {it.get('source'):<8} {c.get('name')} · {c.get('mall')} · image_key={c.get('image_key')}")
    left = [c for c in K.look_coupang_products(look) if c.get("image_key")]
    print("쿠팡 이미지 사본 남음:", len(left), "(0 이어야 정상)")
    if j.get("outfit_id"):
        row = io.view(io.get_outfit(j["outfit_id"]))
        print(json.dumps({k: row.get(k) for k in ("status", "attempts", "cost_usd", "processed_url", "caption_note")},
                         ensure_ascii=False, indent=1))


if __name__ == "__main__":
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
