"""검증용 throwaway — PR-S2 로컬 런타임 검증 (서비스 함수 직접 호출).

엔드포인트(HTTP) 없이 PR-S2a/S2b 서비스 함수를 직접 호출해 한 번에 검증한다:
  1) generate_character_sheet  → 캐릭터 시트 생성 + R2 업로드 URL/로컬 저장
  2) generate_scenes(샘플 씬 2개) → 시트 reference 로 씬 생성 + R2 URL/로컬 저장

WAVESPEED_API_KEY 만 있으면 동작한다(R2_* 까지 있으면 영구 URL, 없으면 WaveSpeed
CDN URL 로 폴백). 프로덕션 파이프라인엔 연결되지 않는다(검증 후 삭제 가능).

실행 (로컬, py 사용):
  cd travel-pipeline
  set WAVESPEED_API_KEY=...                       (Windows)  / export WAVESPEED_API_KEY=...
  # (선택) R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_PUBLIC_BASE_URL
  # (선택, 영구 시트) R2_CHARACTER_BUCKET / R2_CHARACTER_PUBLIC_BASE_URL
  py -m pip install -r requirements.txt           (미설치 시)
  py spikes/verify_sayeon_s2.py

  # 이미 만든 시트가 있으면 시트 생성 생략하고 씬만:
  py spikes/verify_sayeon_s2.py --sheet-url https://.../sheet.png --anchor "early 20s woman, ..."

확인 포인트(육안):
  - 시트가 R2 영구 URL 로 올라갔는가(persistent=True). 안 그러면 R2_* 설정 필요
  - 씬 2장이 시트와 동일 인물·웹툰 스타일인가, 이미지에 글자가 없는가
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# travel-pipeline 패키지 루트를 import 경로에 추가하고 cwd 로 맞춘다
# (spikes/ 아래에서 실행해도 adapters/·services/ 를 찾도록).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv()  # travel-pipeline/.env 가 있으면 키를 읽는다
except Exception:  # noqa: BLE001
    pass

from services.sayeon_character import generate_character_sheet  # noqa: E402
from services.sayeon_scene import generate_scenes  # noqa: E402

OUT_ROOT = Path(__file__).resolve().parent / "output" / "verify_s2"

# 검증용 샘플 캐릭터(설정 폼과 동일한 필드). 독특한 시그니처일수록 일관성 검증이 쉽다.
SAMPLE_CHARACTER = {
    "gender": "woman",
    "age": "early 20s",
    "face": "soft round face, gentle eyes",
    "hair": "long wavy auburn hair",
    "outfit": "beige oversized knit cardigan over a white tee",
    "accessories": "round thin-rim glasses, a small gold star-shaped earring",
    "signature": "round glasses + star earring + auburn waves",
    "extra": "",
}

# PR-S1 산출물을 흉내낸 샘플 씬 2개(감정·배경이 다름 → 드리프트 확인).
SAMPLE_SCENES = [
    {
        "index": 1,
        "image_prompt": "standing alone under a streetlight in the rain at night, "
        "holding a transparent umbrella, looking down sadly, plain dark background",
    },
    {
        "index": 2,
        "image_prompt": "walking on a bright sunny street in the morning, "
        "smiling softly, plain background",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(description="PR-S2 로컬 검증 (서비스 직접 호출)")
    parser.add_argument("--channel-id", default="verify-s2", help="채널 id")
    parser.add_argument("--sheet-url", help="기존 시트 URL (있으면 시트 생성 생략)")
    parser.add_argument("--anchor", default="", help="--sheet-url 사용 시 정체성 앵커")
    parser.add_argument("--sheet-model", default=None, help="시트 생성 모델(미지정=기본)")
    parser.add_argument("--num-images", type=int, default=2, help="씬당 후보 장수")
    parser.add_argument("--seed", type=int, default=-1, help="고정 seed(>=0)")
    args = parser.parse_args()

    if not os.environ.get("WAVESPEED_API_KEY"):
        raise SystemExit("WAVESPEED_API_KEY 미설정 — 환경변수로 키를 주세요.")

    r2_on = all(
        os.environ.get(k)
        for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_PUBLIC_BASE_URL")
    )
    print(f"R2 설정: {'있음' if r2_on else '없음(→ CDN URL 폴백, 시트 비영구)'}")

    # ── 1) 캐릭터 시트 ────────────────────────────────────────────────
    if args.sheet_url:
        sheet_url = args.sheet_url
        anchor = args.anchor
        persistent = None
        print(f"\n① 시트 재사용: {sheet_url}")
    else:
        print("\n① 캐릭터 시트 생성 중 (generate_character_sheet)...")
        sheet = generate_character_sheet(
            args.channel_id,
            SAMPLE_CHARACTER,
            sheet_model=args.sheet_model,
            output_dir=str(OUT_ROOT / "characters" / args.channel_id),
            progress_cb=lambda pct, msg: print(f"   {pct:3d}% {msg}"),
        )
        sheet_url = sheet["sheet_url"]
        anchor = sheet["anchor"]
        persistent = sheet["persistent"]
        print(f"   시트 URL : {sheet_url}")
        print(f"   영구저장 : {persistent}  (모델: {sheet['model']}, ${sheet['cost_usd']})")
        print(f"   앵커     : {anchor}")
        print(f"   로컬     : {OUT_ROOT / 'characters' / args.channel_id / 'sheet.png'}")

    if not sheet_url:
        raise SystemExit("시트 URL 이 비어 있습니다 — 시트 생성 실패.")

    # ── 2) 씬 생성 ────────────────────────────────────────────────────
    print("\n② 씬 생성 중 (generate_scenes, 샘플 씬 2개)...")
    job_id = "verify-s2"
    scenes = generate_scenes(
        job_id,
        sheet_url,
        SAMPLE_SCENES,
        anchor=anchor,
        num_images=args.num_images,
        seed=args.seed,
        output_dir=str(OUT_ROOT / "scenes" / job_id),
        progress_cb=lambda pct, msg: print(f"   {pct:3d}% {msg}"),
    )
    for s in scenes["scenes"]:
        print(f"   씬 {s['index']}: 후보 {s['candidate_count']}장")
        for i, url in enumerate(s["image_urls"], 1):
            print(f"      [{i}] {url}")
    print(f"   총 비용(추정): ${scenes['total_cost_usd']}")
    print(f"   로컬: {OUT_ROOT / 'scenes' / job_id}")

    # ── 결과 체크리스트 ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("[검증 체크리스트]")
    if persistent is False:
        print("  ⚠ 시트가 R2에 영구 저장되지 않음(CDN 폴백). 머지 전 R2_* 설정 권장.")
    elif persistent is True:
        print("  ✓ 시트 R2 영구 업로드 성공")
    print(
        "  [ ] 씬 2장이 시트와 동일 인물인가 (얼굴/헤어·시그니처)\n"
        "  [ ] 웹툰(플랫 컬러·셀 셰이딩) 스타일 유지\n"
        "  [ ] 이미지에 글자/자막 없음\n"
        "→ 통과 시 PR-S2 머지 진행."
    )


if __name__ == "__main__":
    main()
