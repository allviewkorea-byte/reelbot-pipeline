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
    """
    영상 클립과 나레이션 음성을 합성.
    음성 길이에 맞게 영상을 루프하거나 트리밍.
    """
    print(f"  [compose] {spot.name_ko} 영상+음성 합성 중...")

    out_path = Path(config.videos_dir) / f"{spot.id}_with_audio.mp4"

    _run_ffmpeg([
        "-stream_loop", "-1",        # 영상 루프 (음성 길이에 맞게)
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",                  # 음성 끝나면 컷
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
    """
    관광지 이름 자막 오버레이 추가 (하단 위치).
    """
    print(f"  [compose] {spot.name_ko} 자막 추가 중...")

    out_path = Path(config.videos_dir) / f"{spot.id}_subtitled.mp4"

    title_text = spot.name_ko
    subtitle_filter = (
        f"drawtext=text='{title_text}'"
        f":fontsize=72"
        f":fontcolor=white"
        f":borderw=4"
        f":bordercolor=black"
        f":x=(w-text_w)/2"
        f":y=h-text_h-120"
        f":enable='between(t,0,3)'"
    )

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


def concatenate_clips(
    clip_paths: list[Path],
    config: Config,
    output_name: str = "bangkok_travel_final.mp4",
) -> Path:
    """
    모든 클립을 하나의 최종 영상으로 이어 붙임.
    """
    print("  [compose] 최종 영상 합치는 중...")

    # 파일 목록 텍스트 생성
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
    """
    배경음악 믹싱 (나레이션 -0dB, 배경음악 -15dB).
    선택 사항: music_path가 없으면 원본 반환.
    """
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
