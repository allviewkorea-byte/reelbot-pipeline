"""
KIE (Kling Image-to-video Engine) API 클라이언트.
brief.json의 씬 목록을 받아 영상을 자동 생성한다.

API: https://api.klingai.com (Kling AI by Kuaishou)
Auth: Authorization: Bearer {KIE_API_KEY}
"""

import time
import base64
import requests
from pathlib import Path
from config import Config

KIE_API_BASE = "https://api.klingai.com"
MAX_RETRIES = 2
POLL_INTERVAL = 30   # 초
POLL_TIMEOUT = 900   # 최대 15분


def _to_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def _headers(config: Config) -> dict:
    return {
        "Authorization": f"Bearer {config.kie_api_key}",
        "Content-Type": "application/json",
    }


def _submit(scene: dict, char_ref: Path | None, config: Config) -> str:
    """영상 생성 작업 제출 → task_id 반환."""
    payload = {
        "model_name": "kling-v1",
        "prompt": scene["prompt_en"],
        "duration": scene["duration_sec"],
        "aspect_ratio": "9:16",
        "cfg_scale": 0.5,
        "mode": "std",
    }

    if char_ref and char_ref.exists():
        payload["image"] = f"data:image/png;base64,{_to_b64(char_ref)}"

    resp = requests.post(
        f"{KIE_API_BASE}/v1/videos/image2video",
        json=payload,
        headers=_headers(config),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("code", 0) != 0:
        raise RuntimeError(f"KIE 제출 오류: {data.get('message', data)}")

    return data["data"]["task_id"]


def _poll(task_id: str, config: Config) -> str:
    """완료까지 30초 간격 폴링 → 영상 URL 반환."""
    elapsed = 0
    while elapsed < POLL_TIMEOUT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

        resp = requests.get(
            f"{KIE_API_BASE}/v1/videos/image2video/{task_id}",
            headers=_headers(config),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        status = data["task_status"]

        if status == "succeed":
            return data["task_result"]["videos"][0]["url"]
        if status == "failed":
            msg = data.get("task_status_msg", "알 수 없는 오류")
            raise RuntimeError(f"KIE 생성 실패: {msg}")

        print(f"    [kie] {task_id[:10]}… 상태: {status} ({elapsed}s)")

    raise TimeoutError(f"KIE 타임아웃 (task_id={task_id}, {POLL_TIMEOUT}s 초과)")


def _download(url: str, dest: Path):
    resp = requests.get(url, timeout=180, stream=True)
    resp.raise_for_status()
    with dest.open("wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 64):
            f.write(chunk)


def generate_kie_clips(brief: dict, brief_dir: Path, config: Config) -> list[Path]:
    """
    brief["scenes"]의 모든 씬에 대해 KIE API로 영상 생성.
    - 이미 clips/에 mp4가 있으면 재사용 (캐시)
    - 실패 시 최대 MAX_RETRIES(2)회 재시도
    - 완료된 mp4 Path 목록 반환 (실패 씬은 제외)
    """
    clips_dir = brief_dir / "clips"
    clips_dir.mkdir(exist_ok=True)
    char_ref = brief_dir / "character_ref.png"

    results: list[Path] = []
    scenes = brief["scenes"]
    total = len(scenes)

    for i, scene in enumerate(scenes, 1):
        dest = clips_dir / scene["file_name"]
        label = f"{scene['scene_id']} ({scene['spot_name_ko']})"

        if dest.exists():
            print(f"  [kie] ({i}/{total}) 캐시 사용: {dest.name}")
            results.append(dest)
            continue

        success = False
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"  [kie] ({i}/{total}) {label} — 제출 중 (시도 {attempt}/{MAX_RETRIES})")
                task_id = _submit(scene, char_ref, config)
                print(f"  [kie] task_id={task_id[:16]}… 완료 대기 중")

                video_url = _poll(task_id, config)
                _download(video_url, dest)

                print(f"  [kie] 완료: {dest.name}")
                results.append(dest)
                success = True
                break

            except Exception as e:
                print(f"  [kie] 실패 (시도 {attempt}/{MAX_RETRIES}): {e}")
                if attempt == MAX_RETRIES:
                    print(f"  [kie] {label} 건너뜀 — 최대 재시도 초과")

        if not success:
            continue

    print(f"\n  [kie] 완료 {len(results)}/{total}개 클립")
    return results
