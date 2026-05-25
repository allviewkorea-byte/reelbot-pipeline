"""
AI 여행 유튜브 채널 자동화 파이프라인
방콕 여행 브이로그 생성 → YouTube 업로드

실행: python main.py [--skip-video] [--skip-upload] [--spots SPOT_ID ...]
          [--duration {1,2,4}] [--scenario {A,B}] [--seedance-mode {manual,kie}]
"""
from dotenv import load_dotenv
load_dotenv()
import argparse
import json
import shutil
import sys
import traceback
from pathlib import Path

from config import Config, BANGKOK_SPOTS
from character import generate_character_image
from streetview import capture_street_view, check_street_view_availability
from video_gen import generate_video_from_image
from narration import generate_script, generate_audio, generate_intro_outro_script
from compose import merge_video_audio, add_subtitles_overlay, concatenate_clips, add_background_music
from upload import upload_to_youtube
from manual_brief import generate_manual_brief, _seedance_scene_count, _find_latest_brief_dir, validate_clips
from kie_client import generate_kie_clips
from cost_tracker import CostTracker, print_cost_estimate


DURATION_SCENE_COUNT = {1: 6, 2: 12, 4: 24}


# ──────────────────────────────────────────────────────────────────────
#  모듈화된 재사용 함수 (FastAPI 백엔드에서 호출)
#  기존 CLI(run_pipeline) 흐름과는 독립적 — 아래 함수들은 CLI를 깨지 않는다.
# ──────────────────────────────────────────────────────────────────────


def _strip_code_fence(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def generate_scenario(country: str, duration_min: int, config: Config | None = None) -> dict:
    """
    Claude API로 여행 영상 시나리오 + 씬 리스트 생성.

    Returns:
        {
          "country": "...",
          "duration_min": 1,
          "scenario": "전체 시나리오 텍스트",
          "scenes": [
            {"scene_id": 1, "location": "...", "description": "...",
             "camera": "wide shot", "narration": "한국어 나레이션",
             "prompt_en": "english prompt for video", "duration_sec": 5},
            ...
          ]
        }
    """
    import anthropic

    if config is None:
        config = Config()

    scene_count = DURATION_SCENE_COUNT.get(duration_min, 6)

    system_prompt = (
        "너는 트렌디한 한국 여성 여행 유튜버의 영상 시나리오를 짜는 PD야. "
        f"{country} 여행 숏폼 영상의 씬 구성을 만든다. "
        f"정확히 {scene_count}개의 씬을 만들어. "
        "각 씬은 한 장소/한 동작 중심의 9:16 세로 영상이야. "
        "JSON으로만 응답하고, 다음 스키마를 지켜:\n"
        "{\n"
        '  "scenario": "전체 시나리오 요약 (한국어, 2~3문장)",\n'
        '  "scenes": [\n'
        '    {"scene_id": 1, "location": "장소명(영문)", '
        '"description": "씬에서 일어나는 행동/구도(영문)", '
        '"camera": "카메라 앵글(예: wide shot, close-up)", '
        '"narration": "한국어 나레이션 (60~80자)", '
        '"prompt_en": "Kling 영상 생성용 영어 프롬프트", '
        '"duration_sec": 5}\n'
        "  ]\n"
        "}"
    )

    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2048,
        system=system_prompt,
        messages=[{
            "role": "user",
            "content": f"{country} {duration_min}분짜리 여행 숏폼 시나리오를 만들어줘.",
        }],
    )

    data = json.loads(_strip_code_fence(message.content[0].text))
    return {
        "country": country,
        "duration_min": duration_min,
        "scenario": data.get("scenario", ""),
        "scenes": data.get("scenes", []),
    }


def _generate_tts(text: str, out_path: Path, config: Config) -> Path | None:
    """나레이션 텍스트를 Edge TTS로 음성 파일 생성. 실패 시 None."""
    if not text:
        return None
    try:
        import asyncio
        import edge_tts

        async def _run():
            communicate = edge_tts.Communicate(text, config.tts_voice, rate=config.tts_rate)
            await communicate.save(str(out_path))

        asyncio.run(_run())
        return out_path
    except Exception as e:
        print(f"  [tts] 음성 생성 실패 (건너뜀): {e}")
        return None


def generate_video_from_storyboard(
    scenes: list[dict],
    approved_storyboards: list[dict],
    output_dir: str,
    scenario_mode: str = "B",
    seedance_mode: str = "kie",
    config: Config | None = None,
    progress_callback=None,
    video_model: str = "default",
    character_id: str | None = None,
) -> dict:
    """
    승인된 콘티 이미지를 reference로 Kling 영상 생성 후 합성.

    Args:
        scenes: generate_scenario()가 만든 씬 리스트
        approved_storyboards: [{"scene_id": 1, "image_path": "..."}, ...]
        output_dir: 출력 폴더 (예: output/video/{job_id}/)
        scenario_mode: "A"(풀 영상) / "B"(하이브리드) — 현재는 메타로만 기록
        seedance_mode: "kie"(자동) / "manual"(브리프만 생성)
        progress_callback: callable(progress:int 0-100, step:str)

    Returns:
        {"final_video": "...", "clips": [...], "mode": "kie"} 또는
        {"brief_dir": "...", "mode": "manual"}
    """
    import asyncio

    from adapters import VideoGenerationRequest, get_video_adapter
    from adapters.utils import load_character_references

    if config is None:
        config = Config()

    adapter = get_video_adapter(video_model)
    out_dir = Path(output_dir)
    clips_dir = out_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    storyboard_by_id = {sb.get("scene_id"): sb.get("image_path") for sb in approved_storyboards}

    # 작업 3-4: Character ID 지원 모델(Kling v3 등)에는 캐릭터 3면 reference를 자동 전달.
    # 기존 Kling v1 경로는 콘티 프레임을 start image로 사용(동작 보존).
    character_refs = load_character_references(character_id) if character_id else []

    def _report(progress: int, step: str):
        if progress_callback:
            progress_callback(progress, step)
        print(f"  [video] {progress}% — {step}")

    if seedance_mode == "manual":
        # MVP: manual 모드는 자동 영상 생성 대신 안내만 반환 (Phase 2에서 resume 흐름 연동)
        _report(100, "manual 모드 — 콘티 승인본 저장 완료")
        return {
            "mode": "manual",
            "output_dir": str(out_dir),
            "scenes": scenes,
            "approved_storyboards": approved_storyboards,
            "note": "manual 모드는 클립을 직접 생성해야 합니다 (Phase 2 연동 예정).",
        }

    total_steps = len(scenes) + 1  # 씬별 Kling + 최종 합성
    clip_paths: list[Path] = []

    for i, scene in enumerate(scenes, 1):
        scene_id = scene.get("scene_id", i)
        _report(int((i - 1) / total_steps * 100), f"씬 {scene_id} 영상 생성 중...")

        ref_path = storyboard_by_id.get(scene_id)
        if adapter.supports_character_id and character_refs:
            references = character_refs
        elif ref_path:
            references = [ref_path]
        else:
            references = None

        dest = clips_dir / f"scene_{scene_id}.mp4"
        request = VideoGenerationRequest(
            prompt=scene.get("prompt_en") or scene.get("description", ""),
            reference_images=references,
            character_id=character_id if adapter.supports_character_id else None,
            aspect_ratio="9:16",
            duration_seconds=scene.get("duration_sec", 5),
            output_path=str(dest),
        )
        result = asyncio.run(adapter.generate(request))
        clip = Path(result.video_path)

        # 나레이션이 있으면 TTS 합성
        narration = scene.get("narration")
        if narration:
            audio_path = out_dir / f"scene_{scene_id}_narration.mp3"
            audio = _generate_tts(narration, audio_path, config)
            if audio:
                merged = _merge_clip_audio(clip, audio, scene_id, config, out_dir)
                clip = merged

        clip_paths.append(clip)

    _report(int(len(scenes) / total_steps * 100), "최종 영상 합성 중...")
    final_video = _concat_clips(clip_paths, out_dir, config)

    result = {
        "mode": "kie",
        "final_video": str(final_video),
        "clips": [str(p) for p in clip_paths],
        "scenario_mode": scenario_mode,
    }

    # Railway 휘발성 디스크 대응: 완성 영상을 Supabase Storage에 올려 영구 공개 URL을
    # result.video_url 로 반환한다. 업로드 성공 시 로컬 mp4 는 삭제(디스크 절약).
    # SUPABASE 미설정/업로드 실패 시엔 로컬 파일을 유지하고 video_url 을 생략한다.
    from adapters import supabase_storage

    if supabase_storage.is_available():
        try:
            _report(100, "영상 업로드 중...")
            video_url = supabase_storage.upload_video(str(final_video), out_dir.name)
            result["video_url"] = video_url
            shutil.rmtree(clips_dir, ignore_errors=True)
            final_video.unlink(missing_ok=True)
        except Exception as e:
            print(f"  [video] Supabase 업로드 실패 — 로컬 파일 유지: {e}")

    _report(100, "완료")
    return result


def _merge_clip_audio(clip: Path, audio: Path, scene_id, config: Config, out_dir: Path) -> Path:
    """클립 + 나레이션 음성 합성 (ffmpeg). compose.py와 동일 패턴."""
    import subprocess

    out_path = out_dir / "clips" / f"scene_{scene_id}_with_audio.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(clip),
        "-i", str(audio),
        "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-vf", f"scale={config.video_width}:{config.video_height}:force_original_aspect_ratio=decrease,"
               f"pad={config.video_width}:{config.video_height}:(ow-iw)/2:(oh-ih)/2:black",
        "-r", str(config.video_fps),
        "-movflags", "+faststart",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [video] 음성 합성 실패, 원본 클립 사용: {result.stderr[:200]}")
        return clip
    return out_path


def _concat_clips(clip_paths: list[Path], out_dir: Path, config: Config) -> Path:
    """모든 클립을 하나로 이어붙임 (ffmpeg concat)."""
    import subprocess

    concat_list = out_dir / "concat_list.txt"
    concat_list.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in clip_paths),
        encoding="utf-8",
    )
    out_path = out_dir / "final.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"최종 합성 실패: {result.stderr}")
    return out_path


def parse_args():
    parser = argparse.ArgumentParser(
        description="AI 방콕 여행 유튜브 파이프라인",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python main.py
  python main.py --duration 4 --scenario A --seedance-mode kie
  python main.py --duration 1 --scenario B --seedance-mode manual --skip-upload
  python main.py --spots wat_arun khao_san --skip-upload
        """,
    )
    parser.add_argument(
        "--skip-video",
        action="store_true",
        help="Seedance 영상 생성 건너뜀 (이미 생성된 영상 사용)",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="YouTube 업로드 건너뜀",
    )
    parser.add_argument(
        "--spots",
        nargs="+",
        metavar="SPOT_ID",
        help="처리할 관광지 ID 지정 (기본: 전체). 예: --spots wat_arun grand_palace",
    )
    parser.add_argument(
        "--bgm",
        type=str,
        default=None,
        metavar="PATH",
        help="배경음악 파일 경로 (선택, MP3)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        choices=[1, 2, 4],
        default=2,
        metavar="{1,2,4}",
        help="영상 길이(분). 1=6씬, 2=12씬, 4=24씬 (기본값: 2)",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        choices=["A", "B"],
        default="B",
        metavar="{A,B}",
        help=(
            "시나리오 모드. "
            "A=풀 Seedance(모든 씬 영상 클립), "
            "B=스마트 하이브리드(1/3 Seedance + 2/3 정지샷) (기본값: B)"
        ),
    )
    parser.add_argument(
        "--seedance-mode",
        type=str,
        choices=["manual", "kie"],
        default="manual",
        metavar="{manual,kie}",
        help=(
            "영상 생성 모드. "
            "manual=수동(시스템이 브리프 생성, 사용자가 직접 생성), "
            "kie=자동(KIE API 호출) (기본값: manual)"
        ),
    )
    parser.add_argument(
        "--brief-dir",
        type=str,
        default=None,
        metavar="PATH",
        help="manual 모드 재개 시 브리프 폴더 경로 직접 지정 (--resume과 함께 사용 가능).",
    )
    parser.add_argument(
        "--resume",
        nargs="?",
        const="auto",
        default=None,
        metavar="PATH",
        help=(
            "manual 모드 재개. "
            "PATH 없으면 outputs/seedance_brief_*/ 중 최신 폴더 자동 감지. "
            "clips/ 의 mp4 존재 여부를 검증 후 파이프라인 계속 진행."
        ),
    )
    return parser.parse_args()


def ensure_output_dirs(config: Config):
    for d in [config.images_dir, config.videos_dir, config.audio_dir, config.final_dir]:
        Path(d).mkdir(parents=True, exist_ok=True)


def run_pipeline():
    args = parse_args()
    config = Config()

    # args → config 저장 (로직은 이후 단계에서 구현)
    config.duration = args.duration
    config.scene_count = DURATION_SCENE_COUNT[args.duration]
    config.scenario = args.scenario
    config.seedance_mode = args.seedance_mode

    print("=" * 60)
    print("  AI 방콕 여행 유튜브 파이프라인 시작")
    print("=" * 60)
    print(f"  duration     : {args.duration}분 ({config.scene_count}씬)")
    print(f"  scenario     : {args.scenario}  ({'풀 Seedance' if args.scenario == 'A' else '스마트 하이브리드'})")
    print(f"  seedance-mode: {args.seedance_mode}  ({'KIE API 자동' if args.seedance_mode == 'kie' else '수동 브리프'})")
    print("=" * 60)

    # API 키 검증
    try:
        config.validate()
    except EnvironmentError as e:
        print(f"\n[오류] {e}")
        print("환경변수를 설정하거나 .env 파일을 확인해주세요.")
        sys.exit(1)

    ensure_output_dirs(config)

    # KIE 모드 키 검증
    if config.seedance_mode == "kie" and not config.kie_api_key:
        print("[오류] --seedance-mode kie 사용 시 KIE_API_KEY 환경변수가 필요합니다.")
        sys.exit(1)

    cost = CostTracker()

    # 처리할 관광지 필터링
    spots = BANGKOK_SPOTS
    if args.spots:
        spots = [s for s in BANGKOK_SPOTS if s.id in args.spots]
        if not spots:
            print(f"[오류] 유효한 관광지 ID가 없습니다: {args.spots}")
            sys.exit(1)

    print(f"\n처리 관광지: {', '.join(s.name_ko for s in spots)}")
    print(f"총 {len(spots)}개 관광지\n")

    # ── 예상 비용 출력 ────────────────────────────────────────────────
    seedance_count = _seedance_scene_count(config)
    print_cost_estimate(config, num_spots=len(spots), seedance_scene_count=seedance_count)

    # ── Step 1: 나레이션 스크립트 생성 (Claude API) ──────────────────
    print("[1/5] 나레이션 스크립트 생성 중...")
    scripts = generate_script(spots, config)
    cost.add_claude()

    # ── Step 2: 관광지별 이미지 생성 및 음성 변환 ──────────────────
    print("\n[2/5] 이미지 생성 및 음성 변환 중...")
    spot_assets = {}  # spot.id → {character, streetview, audio}

    for spot in spots:
        print(f"\n  ▶ {spot.name_ko}")
        try:
            character_img = generate_character_image(spot, config)
            cost.add_image()
            streetview_img = capture_street_view(spot, config)
            cost.add_streetview()
            script_text = scripts.get(spot.id, spot.description_ko)
            audio_path = generate_audio(spot, script_text, config)

            spot_assets[spot.id] = {
                "character": character_img,
                "streetview": streetview_img,
                "audio": audio_path,
                "script": script_text,
            }
        except Exception as e:
            print(f"  [경고] {spot.name_ko} 처리 실패: {e}")
            traceback.print_exc()
            continue

    if not spot_assets:
        print("\n[오류] 처리된 관광지가 없습니다. 파이프라인 종료.")
        sys.exit(1)

    # ── Step 3: 영상 생성 ─────────────────────────────────────────
    print("\n[3/5] AI 영상 생성 중...")
    video_clips = []

    if args.resume is not None:
        # ── --resume: clips/ 검증 후 파이프라인 재개 ─────────────────
        try:
            if args.resume != "auto":
                brief_dir = Path(args.resume)
            elif args.brief_dir:
                brief_dir = Path(args.brief_dir)
            else:
                brief_dir = _find_latest_brief_dir()
        except FileNotFoundError as e:
            print(f"\n[오류] {e}")
            sys.exit(1)

        print(f"\n  [resume] 브리프 폴더: {brief_dir}")
        found, missing = validate_clips(brief_dir)

        if missing:
            print(f"\n[오류] 누락된 클립 {len(missing)}개:")
            for fname in missing:
                print(f"  ✗ clips/{fname}")
            print(f"\n  {len(found)}/{len(found) + len(missing)}개 완료")
            print(f"  나머지 작업 후 다시 실행: python main.py --resume")
            sys.exit(1)

        print(f"  [resume] 모든 클립 확인 완료 ({len(found)}개) — 파이프라인 재개")

        active_spots = [s for s in spots if s.id in spot_assets]
        for clip_file in sorted(found):
            idx = int(clip_file.stem.split("_")[1]) - 1
            spot = active_spots[idx % len(active_spots)]
            assets = spot_assets[spot.id]
            print(f"\n  ▶ {clip_file.name} → {spot.name_ko}")
            try:
                merged = merge_video_audio(clip_file, assets["audio"], spot, config)
                subtitled = add_subtitles_overlay(merged, spot, config)
                video_clips.append(subtitled)
            except Exception as e:
                print(f"  [경고] {clip_file.name} 처리 실패: {e}")
                traceback.print_exc()

    elif config.seedance_mode == "manual":
        # ── manual 모드: 브리프 패키지 생성 후 일시정지 ──────────────
        print("\n  [manual] 브리프 패키지 생성 중...")
        brief_dir = generate_manual_brief(
            spots=[s for s in spots if s.id in spot_assets],
            spot_assets=spot_assets,
            config=config,
        )
        print()
        print("=" * 56)
        print("  ✋ 수동 작업 대기 중")
        print("=" * 56)
        print(f"  📁 폴더: {brief_dir.resolve()}")
        print(f"  📋 todo.md 파일을 열고 작업 진행해주세요")
        print()
        print(f"  ✅ 모든 클립 완료 후: python main.py --resume")
        print("=" * 56)
        sys.exit(0)

    else:
        # ── kie 모드: brief 생성 → KIE API 자동 호출 ─────────────────
        active_spots = [s for s in spots if s.id in spot_assets]

        print("\n  [kie] 브리프 생성 중...")
        brief_dir = generate_manual_brief(
            spots=active_spots,
            spot_assets=spot_assets,
            config=config,
        )

        import json
        brief = json.loads((brief_dir / "brief.json").read_text(encoding="utf-8"))

        print(f"\n  [kie] KIE API 영상 생성 시작 ({len(brief['scenes'])}개 씬)")
        clip_paths = generate_kie_clips(brief, brief_dir, config)

        for clip_path in clip_paths:
            cost.add_kie_clip()
            # scene 순서 기반으로 관광지 매핑
            idx = int(clip_path.stem.split("_")[1]) - 1
            spot = active_spots[idx % len(active_spots)]
            assets = spot_assets[spot.id]

            try:
                merged = merge_video_audio(clip_path, assets["audio"], spot, config)
                subtitled = add_subtitles_overlay(merged, spot, config)
                video_clips.append(subtitled)
            except Exception as e:
                print(f"  [경고] {clip_path.name} 합성 실패: {e}")
                traceback.print_exc()

    if not video_clips:
        print("\n[오류] 생성된 영상 클립이 없습니다.")
        sys.exit(1)

    # ── Step 4: 최종 영상 합성 ────────────────────────────────────
    print("\n[4/5] 최종 영상 합성 중...")
    final_video = concatenate_clips(video_clips, config)

    # 배경음악 (선택)
    if args.bgm:
        bgm_path = Path(args.bgm)
        final_video = add_background_music(final_video, bgm_path, config)

    print(f"\n  최종 영상: {final_video}")
    print(f"  파일 크기: {final_video.stat().st_size / 1024 / 1024:.1f} MB")

    # ── Step 5: YouTube 업로드 ─────────────────────────────────────
    if args.skip_upload:
        print("\n[5/5] YouTube 업로드 건너뜀 (--skip-upload)")
    else:
        print("\n[5/5] YouTube 업로드 중...")
        try:
            video_id = upload_to_youtube(final_video, config)
            print(f"\n  YouTube URL: https://www.youtube.com/watch?v={video_id}")
        except Exception as e:
            print(f"\n  [경고] YouTube 업로드 실패: {e}")
            print(f"  최종 영상은 다음 경로에 저장됨: {final_video}")

    cost.print_summary(label="실제 사용 비용")

    print("\n" + "=" * 60)
    print("  파이프라인 완료!")
    print("=" * 60)


if __name__ == "__main__":
    run_pipeline()
