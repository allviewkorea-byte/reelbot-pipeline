import json
import math
import shutil
from datetime import datetime
from pathlib import Path
from typing import List

from config import Config, BangkokSpot

# 씬별 한국어 비디오 프롬프트 (관광지 순환)
_VIDEO_PROMPTS_KO = {
    "wat_arun":     "왓아룬 사원 탑 앞에서 캐릭터가 카메라를 바라보며 미소짓고 손을 흔듦",
    "grand_palace": "황금빛 왕궁 정문 앞에서 캐릭터가 두 손을 모아 합장 인사",
    "khao_san":     "카오산로드 거리를 걸으며 캐릭터가 주변 야시장을 둘러보고 엄지 척",
    "asiatique":    "아시아티크 야경 배경으로 캐릭터가 대관람차를 가리키며 미소",
    "siam_square":  "씨암스퀘어 쇼핑가를 걸으며 캐릭터가 쇼핑백 들고 트렌디하게 포즈",
}

_VIDEO_PROMPTS_EN = {
    "wat_arun":     "Stylish Korean woman standing in front of Wat Arun temple, smiling and waving at the camera, cinematic travel vlog, vertical 9:16.",
    "grand_palace": "Stylish Korean woman at the Grand Palace gate, hands in prayer gesture, golden rooftop in background, vertical 9:16.",
    "khao_san":     "Stylish Korean woman walking Khao San Road night market, looking around excitedly, thumbs up, vertical 9:16.",
    "asiatique":    "Stylish Korean woman at Asiatique riverside, pointing at Ferris wheel, city lights reflection, vertical 9:16.",
    "siam_square":  "Stylish Korean woman walking Siam Square shopping street, holding shopping bags, trendy pose, vertical 9:16.",
}


def _seedance_scene_count(config: Config) -> int:
    """시나리오에 따라 Seedance 클립이 필요한 씬 수 계산."""
    if config.scenario == "A":
        return config.scene_count
    return math.ceil(config.scene_count / 3)  # B: 1/3만 Seedance


def _build_scene_list(spots: List[BangkokSpot], count: int) -> List[dict]:
    """씬을 관광지에 순환 분배."""
    return [
        {"index": i + 1, "spot": spots[i % len(spots)]}
        for i in range(count)
    ]


def _find_latest_brief_dir() -> Path:
    """outputs/seedance_brief_*/ 중 가장 최근 폴더 자동 감지."""
    candidates = sorted(Path("outputs").glob("seedance_brief_*"))
    if not candidates:
        raise FileNotFoundError(
            "outputs/seedance_brief_*/ 폴더를 찾을 수 없습니다.\n"
            "먼저 python main.py --seedance-mode manual 을 실행하세요."
        )
    return candidates[-1]


def validate_clips(brief_dir: Path) -> tuple[list[Path], list[str]]:
    """
    brief.json의 씬 목록과 clips/ 폴더를 대조.
    반환: (존재하는 파일 목록, 누락된 파일명 목록)
    """
    brief_path = brief_dir / "brief.json"
    if not brief_path.exists():
        raise FileNotFoundError(f"brief.json 없음: {brief_path}")

    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    clips_dir = brief_dir / "clips"

    found, missing = [], []
    for scene in brief["scenes"]:
        clip = clips_dir / scene["file_name"]
        if clip.exists():
            found.append(clip)
        else:
            missing.append(scene["file_name"])

    return found, missing


def generate_manual_brief(
    spots: List[BangkokSpot],
    spot_assets: dict,
    config: Config,
) -> Path:
    """
    --seedance-mode manual 전용 브리프 패키지 생성.
    outputs/seedance_brief_YYYYMMDD_HHMMSS/ 구조로 저장.
    생성된 브리프 폴더 경로 반환.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    brief_dir = Path("outputs") / f"seedance_brief_{timestamp}"
    clips_dir = brief_dir / "clips"
    brief_dir.mkdir(parents=True)
    clips_dir.mkdir()

    seedance_count = _seedance_scene_count(config)
    scenes = _build_scene_list(spots, seedance_count)

    print(f"  [manual_brief] 브리프 폴더 생성: {brief_dir}")
    print(f"  [manual_brief] Seedance 씬 수: {seedance_count}개 "
          f"(시나리오 {config.scenario}, 전체 {config.scene_count}씬)")

    # ── 1. 캐릭터 시드 이미지 복사 ───────────────────────────────────
    seeds_dir = Path(config.images_dir) / "seeds"
    if (seeds_dir / "front.png").exists():
        shutil.copy2(seeds_dir / "front.png", brief_dir / "character_ref.png")
        print("  [manual_brief] character_ref.png ← seeds/front.png")
    else:
        for spot in spots:
            if spot.id in spot_assets:
                shutil.copy2(spot_assets[spot.id]["character"], brief_dir / "character_ref.png")
                print(f"  [manual_brief] character_ref.png ← {spot.id}_character.png")
                break

    # ── 2. 씬별 배경 이미지 복사 ─────────────────────────────────────
    for scene in scenes:
        spot = scene["spot"]
        idx = scene["index"]
        if spot.id in spot_assets:
            bg_src = spot_assets[spot.id]["streetview"]
            dst_name = f"scene_{idx:02d}_bg.png"
            shutil.copy2(bg_src, brief_dir / dst_name)
            print(f"  [manual_brief] {dst_name} ← {spot.name_ko}")

    # ── 3. brief.json 생성 ───────────────────────────────────────────
    brief = {
        "generated_at": timestamp,
        "pipeline_settings": {
            "duration_min": config.duration,
            "total_scene_count": config.scene_count,
            "seedance_scene_count": seedance_count,
            "scenario": config.scenario,
            "seedance_mode": "manual",
        },
        "video_settings": {
            "resolution": "720x1280",
            "fps": 30,
            "duration_per_clip_sec": 10,
            "format": "mp4",
        },
        "clips_output_folder": "clips/",
        "scenes": [
            {
                "scene_id": f"scene_{s['index']:02d}",
                "file_name": f"scene_{s['index']:02d}.mp4",
                "spot_id": s["spot"].id,
                "spot_name_ko": s["spot"].name_ko,
                "spot_name_en": s["spot"].name_en,
                "reference_bg": f"scene_{s['index']:02d}_bg.png",
                "reference_character": "character_ref.png",
                "prompt_ko": _VIDEO_PROMPTS_KO.get(s["spot"].id, s["spot"].description_ko),
                "prompt_en": _VIDEO_PROMPTS_EN.get(
                    s["spot"].id,
                    f"Stylish Korean woman traveling in {s['spot'].name_en}, Bangkok. "
                    f"She walks and looks around naturally, smiling at the camera. "
                    f"Cinematic travel vlog style, smooth camera movement. Vertical video 9:16.",
                ),
                "duration_sec": 10,
                "resolution": "720x1280",
            }
            for s in scenes
        ],
    }

    (brief_dir / "brief.json").write_text(
        json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  [manual_brief] brief.json 생성 완료 ({seedance_count}개 씬)")

    # ── 4. todo.md 생성 ──────────────────────────────────────────────
    _write_todo_md(brief_dir, brief, config, seedance_count, timestamp)
    print("  [manual_brief] todo.md 생성 완료")

    return brief_dir


def _write_todo_md(
    brief_dir: Path,
    brief: dict,
    config: Config,
    seedance_count: int,
    timestamp: str,
):
    scenario_label = (
        "A — 풀 Seedance (모든 씬 영상 클립)"
        if config.scenario == "A"
        else "B — 스마트 하이브리드 (1/3 Seedance + 2/3 정지샷)"
    )

    # 씬별 체크리스트 블록 생성
    scene_blocks = []
    for scene in brief["scenes"]:
        idx = scene["scene_id"].split("_")[1]
        block = (
            f"- [ ] `scene_{idx}.mp4`  "
            f"— {scene['spot_name_ko']} ({scene['spot_name_en']})\n"
            f"  - **프롬프트**: \"{scene['prompt_ko']}\"\n"
            f"  - **배경 참고**: `{scene['reference_bg']}`\n"
            f"  - **캐릭터**: `{scene['reference_character']}`\n"
            f"  - **해상도**: {scene['resolution']} / **길이**: {scene['duration_sec']}초"
        )
        scene_blocks.append(block)

    scene_checklist = "\n\n".join(scene_blocks)

    todo_md = f"""# Seedance 수동 작업 체크리스트

생성 시각: {datetime.strptime(timestamp, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")}

---

## 설정 요약

| 항목 | 값 |
|------|----|
| 영상 길이 | {config.duration}분 (전체 {config.scene_count}씬) |
| 시나리오 | {scenario_label} |
| Seedance 씬 수 | {seedance_count}개 |
| 해상도 | 720×1280 (세로형 9:16) |
| 클립 길이 | 10초 |

---

## 작업 방법

1. **[seedance.tv](https://seedance.tv) 접속**
2. 아래 **씬 목록**을 순서대로 확인
3. 각 씬마다 **프롬프트**와 **참고 이미지**를 Seedance에 입력
   - `character_ref.png` → 캐릭터 시드 이미지로 업로드
   - `scene_NN_bg.png` → 배경 참고 이미지로 활용
4. 생성된 mp4를 **지정된 파일명**으로 `clips/` 폴더에 저장
   - 파일명이 정확히 일치해야 합니다 (대소문자 포함)
5. 모든 씬 완료 후 아래 명령어 실행:

```bash
python main.py --resume
```

---

## 씬 목록 ({seedance_count}개)

{scene_checklist}

---

## 폴더 구조

```
{brief_dir.name}/
├── brief.json            ← 씬별 메타데이터 (프롬프트·설정)
├── character_ref.png     ← 캐릭터 시드 이미지
├── scene_01_bg.png       ← 씬별 Street View 배경
│   ...
├── scene_{seedance_count:02d}_bg.png
├── todo.md               ← 이 파일
└── clips/                ← ★ 완성된 mp4 클립을 여기에 저장
    ├── scene_01.mp4      (작업 완료 후)
    └── ...
```

---

> **주의**: `clips/` 안의 파일명이 씬 목록과 다르면 파이프라인이 오류를 냅니다.
> 완료 전 클립 수: {seedance_count}개 필요
"""

    (brief_dir / "todo.md").write_text(todo_md, encoding="utf-8")
