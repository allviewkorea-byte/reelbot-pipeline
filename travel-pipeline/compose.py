import subprocess
from pathlib import Path
from config import Config, BangkokSpot

def _run_ffmpeg(args: list[str]):
    cmd = ["ffmpeg", "-y"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg 오류:\n{result.stderr}")


def merge_video_audio(
    video_path: Path,
    audio_path: Path,
    spot: BangkokSpot,
    config: Config,
) -> Path:
    print(f"  [compose] {spot.name_ko} 영상+음성 합성 중...")
    out_path = Path(config.videos_dir) / f"{spot.id}_with_audio.mp4"

    _run_ffmpeg([
        "-stream_loop", "-1",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-vf", f"scale={config.video_width}:{config.video_height}:force_original_aspect_ratio=decrease,"
               f"pad={config.video_width}:{config.video_height}:(ow-iw)/2:(oh-ih)/2:black",
        "-r", str(config.video_fps),
        "-movflags", "+faststart",
        str(out_path),
    ])

    print(f"  [compose] 저장 완료: {out_path}")
    return out_path


def add_subtitles_overlay(
    video_path: Path,
    spot: BangkokSpot,
    config: Config,
) -> Path:
    print(f"  [compose] {spot.name_ko} 자막 추가 중...")
    out_path = Path(config.videos_dir) / f"{spot.id}_subtitled.mp4"

    # Windows 한국어 폰트 경로 직접 지정
    font_path = "C:/Windows/Fonts/malgun.ttf"
    title_text = spot.name_en  # 한국어 대신 영어 사용 (인코딩 문제 방지)

    subtitle_filter = (
        f"drawtext=fontfile='{font_path}'"
        f":text='{title_text}'"
        f":fontsize=72"
        f":fontcolor=white"
        f":borderw=4"
        f":bordercolor=black"
        f":x=(w-text_w)/2"
        f":y=h-text_h-120"
        f":enable='between(t,0,3)'"
    )

    try:
        _run_ffmpeg([
            "-i", str(video_path),
            "-vf", subtitle_filter,
            "-c:v", "libx264",
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(out_path),
        ])
        print(f"  [compose] 자막 저장 완료: {out_path}")
        return out_path
    except Exception as e:
        # 자막 실패 시 원본 사용
        print(f"  [compose] 자막 추가 실패, 원본 사용: {e}")
        return video_path


def concatenate_clips(
    clip_paths: list[Path],
    config: Config,
    output_name: str = "bangkok_travel_final.mp4",
) -> Path:
    print("  [compose] 최종 영상 합치는 중...")

    concat_list = Path(config.final_dir) / "concat_list.txt"
    lines = [f"file '../videos/{p.name}'\n" for p in clip_paths]
    concat_list.write_text("".join(lines))

    out_path = Path(config.final_dir) / output_name

    _run_ffmpeg([
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    ])

    print(f"  [compose] 최종 영상 완료: {out_path}")
    return out_path


def add_background_music(
    video_path: Path,
    music_path: Path,
    config: Config,
) -> Path:
    if not music_path or not music_path.exists():
        return video_path

    print("  [compose] 배경음악 믹싱 중...")
    out_path = video_path.parent / (video_path.stem + "_bgm.mp4")

    _run_ffmpeg([
        "-i", str(video_path),
        "-stream_loop", "-1",
        "-i", str(music_path),
        "-filter_complex",
        "[0:a]volume=1.0[a1];[1:a]volume=0.15[a2];[a1][a2]amix=inputs=2:duration=first[aout]",
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(out_path),
    ])

    print(f"  [compose] BGM 믹싱 완료: {out_path}")
    return out_path