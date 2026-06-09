"""검증용 throwaway — PR-S5 로컬 검증 (실제 ffmpeg 썸네일 렌더).

기본은 색 PNG 배경 + 하드코딩 hook_text 로 진짜 썸네일 PNG 를 만든다.
--script 를 주면(OPENAI_API_KEY 필요) hook_text 를 LLM 으로 생성한다.
--image 로 실제 S2 씬 이미지를 물릴 수 있다.

ffmpeg + Noto Sans CJK KR 폰트 필요(S4 에서 한글 OK 확인됨). 프로덕션 미연결.

실행:
  cd travel-pipeline
  py spikes/verify_sayeon_s5.py
  py spikes/verify_sayeon_s5.py --image out/scene_3.png
  py spikes/verify_sayeon_s5.py --script "스무 살 때 엄마의 낡은 코트가..."   # LLM 후킹
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
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

from services.sayeon_thumbnail import generate_thumbnail  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "output" / "verify_s5"

SAMPLE_HOOK = "엄마 옷장에\n새 옷이 없던 이유"
SAMPLE_HIGHLIGHT = "새 옷이 없던 이유"


def _make_color_png(dest: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=navy:s=1080x1920",
         "-frames:v", "1", str(dest)],
        check=True, capture_output=True,
    )


def _png_size(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(path)],
        check=True, capture_output=True, text=True,
    )
    w, h = out.stdout.strip().split("x")
    return int(w), int(h)


def main() -> None:
    parser = argparse.ArgumentParser(description="PR-S5 로컬 검증 (generate_thumbnail)")
    parser.add_argument("--image", default=None, help="배경 씬 이미지(없으면 색 PNG)")
    parser.add_argument("--script", default=None, help="주면 LLM 으로 hook 생성")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.image:
        image = args.image
    else:
        p = OUT_DIR / "bg_sample.png"
        _make_color_png(p)
        image = str(p)

    kwargs = {"output_dir": str(OUT_DIR)}
    if args.script:
        if not os.getenv("OPENAI_API_KEY"):
            raise SystemExit("--script 사용 시 OPENAI_API_KEY 필요")
        kwargs["script"] = args.script
        print("LLM 으로 후킹 생성 중...")
    else:
        kwargs["hook_text"] = SAMPLE_HOOK
        kwargs["highlight"] = SAMPLE_HIGHLIGHT

    print("썸네일 렌더 중...\n")
    result = generate_thumbnail(image, **kwargs)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 결과는 R2 미설정 시 로컬 경로. 로컬 파일이면 크기 점검.
    url = result["thumbnail_url"]
    local = OUT_DIR / "thumb.png"
    print("\n" + "=" * 60)
    ok = True
    if local.exists():
        w, h = _png_size(local)
        cond = (w, h) == (1080, 1920)
        print(f"  {'✓' if cond else '✗'} 썸네일 크기 {w}x{h} (기대 1080x1920)")
        ok &= cond
        print(f"  결과물: {local}")
    else:
        print(f"  (로컬 thumb.png 없음 — url={url})")
    if not result["hook_text"]:
        print("  ✗ hook_text 비어있음"); ok = False
    else:
        print(f"  후킹: {result['hook_text']!r}  강조: {result['highlight']!r}")
    print("=" * 60)
    print(f"결과: {'통과 ✅ — thumb.png 열어 글씨/강조/외곽선 확인' if ok else '실패 ✗'}")


if __name__ == "__main__":
    main()
