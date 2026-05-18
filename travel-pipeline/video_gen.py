import time
import base64
import requests
from pathlib import Path
from config import Config, BangkokSpot

SEEDANCE_API_BASE = "https://api.seedance.ai/v1"

def _image_to_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def generate_video_from_image(
    character_img: Path,
    streetview_img: Path,
    spot: BangkokSpot,
    config: Config,
) -> Path:
    """
    Seedance API (ByteDance)로 캐릭터 이미지 → 영상 생성.
    캐릭터 이미지를 기반으로 자연스럽게 움직이는 영상을 만든다.
    """
    print(f"  [video_gen] {spot.name_ko} 영상 생성 요청 중...")

    headers = {
        "Authorization": f"Bearer {config.seedance_api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "seedance-1-lite",
        "image": f"data:image/png;base64,{_image_to_base64(character_img)}",
        "prompt": (
            f"A stylish Korean woman traveling in {spot.name_en}, Bangkok. "
            f"She walks and looks around naturally, smiling at the camera. "
            f"Cinematic travel vlog style, smooth camera movement. "
            f"Vertical video 9:16."
        ),
        "duration": config.video_duration_per_spot,
        "resolution": "1080x1920",
        "fps": config.video_fps,
    }

    # 영상 생성 요청
    resp = requests.post(
        f"{SEEDANCE_API_BASE}/video/generate",
        json=payload,
        headers=headers,
        timeout=60,
    )
    resp.raise_for_status()
    task_id = resp.json()["task_id"]
    print(f"  [video_gen] 작업 ID: {task_id} — 완료 대기 중...")

    # 폴링으로 완료 확인 (최대 10분)
    video_url = _poll_task(task_id, headers, max_wait=600)

    # 영상 다운로드
    out_path = Path(config.videos_dir) / f"{spot.id}_clip.mp4"
    video_data = requests.get(video_url, timeout=120).content
    out_path.write_bytes(video_data)

    print(f"  [video_gen] 저장 완료: {out_path}")
    return out_path


def _poll_task(task_id: str, headers: dict, max_wait: int = 600) -> str:
    """작업 완료까지 폴링. 완료되면 영상 URL 반환."""
    elapsed = 0
    interval = 10

    while elapsed < max_wait:
        time.sleep(interval)
        elapsed += interval

        resp = requests.get(
            f"{SEEDANCE_API_BASE}/video/task/{task_id}",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")

        if status == "completed":
            return data["output"]["video_url"]
        elif status == "failed":
            raise RuntimeError(f"Seedance 영상 생성 실패: {data.get('error', '알 수 없는 오류')}")

        print(f"  [video_gen] 상태: {status} ({elapsed}초 경과)")

    raise TimeoutError(f"Seedance 영상 생성 타임아웃 ({max_wait}초)")
