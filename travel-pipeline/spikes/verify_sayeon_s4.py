"""검증용 throwaway — PR-S4 로컬 검증 (실제 ffmpeg 합성).

기본은 자체 샘플(색 PNG + 무음/길이 맞춘 오디오)로 진짜 mp4 를 만든다. 실제 산출물이
있으면 물려서 검증할 수 있다:
  --audio  spikes/output/verify_s3/narration.wav   (S3 출력)
  --images scene_1.png,scene_2.png,...              (S2 출력, 콤마구분)
  --timings timings.json                            (S3 scene_timings JSON)

ffmpeg/ffprobe + Noto Sans CJK KR 폰트가 필요(자막 번인). 프로덕션 미연결.

실행:
  cd travel-pipeline
  py spikes/verify_sayeon_s4.py
  py spikes/verify_sayeon_s4.py --audio spikes/output/verify_s3/narration.wav \
     --images out/scene_1.png,out/scene_2.png,out/scene_3.png,out/scene_4.png \
     --timings my_timings.json
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

from services.sayeon_assemble import generate_assemble  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "output" / "verify_s4"
SRC_DIR = OUT_DIR / "src"

# 샘플 씬(자막·모션). 모션을 다양하게 섞어 켄번즈/팬을 모두 검증.
SAMPLE = [
    {"index": 1, "subtitle": "스무 살 때, 엄마의 낡은 코트가 부끄러웠어요",
     "highlight": "낡은 코트", "motion": "zoom_in", "color": "navy"},
    {"index": 2, "subtitle": "친구들 앞에서 모른 척했죠",
     "highlight": "모른 척", "motion": "pan_right", "color": "darkred"},
    {"index": 3, "subtitle": "엄마의 서랍에서 낡은 가계부를 발견했어요",
     "highlight": "가계부", "motion": "zoom_out", "color": "darkgreen"},
    {"index": 4, "subtitle": "그 의미를 너무 늦게 알아버렸어요",
     "highlight": "너무 늦게", "motion": "pan_left", "color": "purple"},
]
SAMPLE_DURS = [2.5, 3.0, 2.0, 3.5]


def _make_color_png(color: str, dest: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=1080x1920",
         "-frames:v", "1", str(dest)],
        check=True, capture_output=True,
    )


def _make_silence(seconds: float, dest: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", f"{seconds}", "-c:a", "pcm_s16le", str(dest)],
        check=True, capture_output=True,
    )


def _timings_from_durs(durs: list[float], gap: float = 0.4) -> list[dict]:
    """S3 와 동일한 연속·쉼중앙 타이밍을 흉내내 생성."""
    n = len(durs)
    line_start = [0.0] * n
    cur = 0.0
    for i in range(n):
        line_start[i] = cur
        cur += durs[i] + (gap if i < n - 1 else 0.0)
    total = cur

    def boundary(i):
        return line_start[i] + durs[i] + gap / 2.0
    out = []
    for i in range(n):
        s = 0.0 if i == 0 else boundary(i - 1)
        e = total if i == n - 1 else boundary(i)
        out.append({"index": i + 1, "start": round(s, 3),
                    "end": round(e, 3), "duration": round(e - s, 3)})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="PR-S4 로컬 검증 (generate_assemble)")
    parser.add_argument("--audio", default=None, help="나레이션 오디오(없으면 무음 샘플)")
    parser.add_argument("--images", default=None, help="씬 이미지 경로 콤마구분")
    parser.add_argument("--timings", default=None, help="scene_timings JSON 파일")
    args = parser.parse_args()

    SRC_DIR.mkdir(parents=True, exist_ok=True)

    # 타이밍
    if args.timings:
        timings = json.loads(Path(args.timings).read_text(encoding="utf-8"))
        if isinstance(timings, dict):
            timings = timings["scene_timings"]
    else:
        timings = _timings_from_durs(SAMPLE_DURS)
    total = max(t["end"] for t in timings)

    # 이미지
    if args.images:
        imgs = [p.strip() for p in args.images.split(",") if p.strip()]
    else:
        imgs = []
        for s in SAMPLE:
            p = SRC_DIR / f"scene_{s['index']}.png"
            _make_color_png(s["color"], p)
            imgs.append(str(p))

    # 오디오
    if args.audio:
        audio = args.audio
    else:
        audio_p = SRC_DIR / "narration.wav"
        _make_silence(total, audio_p)
        audio = str(audio_p)

    scenes = []
    for i, s in enumerate(SAMPLE):
        scenes.append({
            "index": s["index"],
            "image_url": imgs[i] if i < len(imgs) else imgs[-1],
            "subtitle": s["subtitle"],
            "highlight": s["highlight"],
            "motion": s["motion"],
        })

    print(f"합성 중... (씬 {len(scenes)}, 목표 길이 ~{round(total,2)}s)\n")
    result = generate_assemble(
        "verify-s4", scenes, timings, audio, output_dir=str(OUT_DIR)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 점검: 출력 길이 ≈ 오디오/타이밍 total
    vid_total = result["total_duration"]
    ok = abs(vid_total - total) < 0.3
    print("\n" + "=" * 60)
    print(f"[자동 점검]  영상 길이={vid_total}s  목표={round(total,2)}s")
    print(f"  {'✓' if ok else '✗'} 길이 일치(±0.3s)")
    print(f"  결과물: {OUT_DIR / 'final.mp4'}")
    print("=" * 60)
    print(f"결과: {'통과 ✅ — final.mp4 재생해 자막 싱크/켄번즈 확인' if ok else '실패 ✗'}")


if __name__ == "__main__":
    main()
