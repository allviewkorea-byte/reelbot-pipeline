"""사연 트랙 — end-to-end 오케스트레이션.

기존 6개 서비스(split → character → scene → tts → assemble → thumbnail)를 순서대로
연결해 '사연 글 → 완성 영상 + 썸네일' 을 한 번에 만든다. 새 로직은 최소화하고
기존 service 함수를 그대로 체인한다(재발명 금지).

캐릭터 시트는 채널당 1회 재사용 원칙이므로, sheet_url+anchor 가 주어지면 시트 생성을
건너뛴다(비용 절감 — 핵심).
"""

from __future__ import annotations

from contextlib import contextmanager

from services.sayeon_assemble import generate_assemble
from services.sayeon_bgm import select_mood
from services.sayeon_character import generate_character_sheet
from services.sayeon_director import apply_director
from services.sayeon_scene import generate_scenes
from services.sayeon_split import split_script
from services.sayeon_thumbnail import generate_thumbnail
from services.sayeon_tts import generate_tts

# 씬당 후보 장수. 자동 파이프라인이라 큐레이션 없이 1장만 뽑아 비용을 줄인다.
_SCENE_NUM_IMAGES = 1


@contextmanager
def _stage(label: str):
    """단계 실패 시 어느 단계인지 메시지에 담아 다시 던진다."""
    try:
        yield
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"[{label}] 단계 실패: {e}") from e


def generate_full(
    job_id: str,
    script: str,
    character_spec: dict | None = None,
    sheet_url: str = "",
    anchor: str = "",
    voice_id: str | None = None,
    num_scenes: int | None = None,
    gap_sec: float = 0.4,
    thumbnail_scene_index: int | None = None,
    progress_cb=None,
) -> dict:
    """사연 글 → 완성 영상 + 썸네일. 6개 서비스를 순서대로 체인한다.

    Returns:
        {video_url, thumbnail_url, audio_url, sheet_url, anchor, scenes, scene_timings}
    """

    def report(pct: int, msg: str) -> None:
        if progress_cb:
            progress_cb(pct, msg)

    def band(lo: int, hi: int):
        """하위 서비스의 0~100 진행률을 [lo, hi] 구간으로 매핑하는 콜백."""
        def cb(p: int, m: str) -> None:
            report(lo + int((hi - lo) * max(0, min(100, p)) / 100), m)
        return cb

    if not script or not script.strip():
        raise ValueError("script(사연 나레이션)가 필요합니다.")

    # a. 씬 분할 (~10%)
    report(2, "씬 분할 중...")
    with _stage("씬 분할"):
        scenes = split_script(script, num_scenes=num_scenes, character_anchor=anchor)["scenes"]
    if not scenes:
        raise RuntimeError("[씬 분할] 결과가 비어 있습니다.")
    report(10, f"씬 {len(scenes)}개 분할 완료")

    # a-2. 디렉터: 씬별 샷 설계 → image_prompt 구성(실패 시 기존 프롬프트 폴백, 안 멈춤)
    report(12, "샷 연출 설계 중...")
    scenes = apply_director(script, scenes)

    # b. 캐릭터 시트 (~25%) — sheet_url+anchor 주어지면 재사용(스킵)
    if sheet_url and anchor:
        report(25, "기존 캐릭터 시트 재사용(생성 스킵)")
    else:
        if not character_spec:
            raise ValueError("sheet_url+anchor 또는 character_spec 중 하나는 필요합니다.")
        with _stage("캐릭터 시트"):
            sheet = generate_character_sheet(
                job_id, character_spec, progress_cb=band(10, 25)
            )
        sheet_url = sheet["sheet_url"]
        anchor = sheet["anchor"]
        report(25, "캐릭터 시트 생성 완료")

    # c. 씬 이미지 (~55%) — 시트 reference 로 동일 인물 씬 생성
    with _stage("씬 이미지"):
        scene_gen = generate_scenes(
            job_id, sheet_url, scenes, anchor=anchor,
            num_images=_SCENE_NUM_IMAGES, progress_cb=band(25, 55),
        )
    image_by_index = {r["index"]: r["selected_url"] for r in scene_gen["scenes"]}
    report(55, "씬 이미지 생성 완료")

    # d. TTS + 타이밍 (~70%)
    with _stage("TTS"):
        tts = generate_tts(
            job_id, scenes, voice_id=voice_id, gap_sec=gap_sec, progress_cb=band(55, 70)
        )
    audio_url = tts["audio_url"]
    scene_timings = tts["scene_timings"]
    report(70, "음성/타이밍 완료")

    # e. 합성 (~90%) — 씬 이미지 + 타이밍 + 자막 + 음성 → mp4
    assemble_scenes = [
        {
            "index": s["index"],
            "image_url": image_by_index.get(s["index"]),
            "subtitle": s.get("subtitle", ""),
            "highlight": s.get("highlight", ""),
            "motion": s.get("motion", "zoom_in"),
            "emotion": s.get("emotion", ""),  # 감정 피크 씬 자막 강조용
        }
        for s in scenes
    ]
    missing = [s["index"] for s in assemble_scenes if not s["image_url"]]
    if missing:
        raise RuntimeError(f"[합성] 씬 이미지 누락: {missing}")
    # 씬 감정 분포로 BGM 분위기 선택(emotional|suspense|hopeful). 결말 긍정이면 hopeful.
    bgm_mood = select_mood(emotions=[s.get("emotion", "") for s in scenes])
    with _stage("합성"):
        asm = generate_assemble(
            job_id, assemble_scenes, scene_timings, audio_url,
            progress_cb=band(70, 90), bgm_mood=bgm_mood,
        )
    video_url = asm["video_url"]
    report(90, "영상 합성 완료")

    # f. 썸네일 (~98%) — 지정 씬(또는 기본=첫 씬) 이미지 + script 후킹
    if thumbnail_scene_index in image_by_index:
        thumb_image = image_by_index[thumbnail_scene_index]
    else:
        thumb_image = image_by_index.get(scenes[0]["index"]) or next(
            iter(image_by_index.values())
        )
    with _stage("썸네일"):
        thumb = generate_thumbnail(thumb_image, script=script)
    thumbnail_url = thumb["thumbnail_url"]
    report(98, "썸네일 완료")

    report(100, "완료")
    out_scenes = [
        {**s, "image_url": image_by_index.get(s["index"])} for s in scenes
    ]
    return {
        "video_url": video_url,
        "thumbnail_url": thumbnail_url,
        "audio_url": audio_url,
        "sheet_url": sheet_url,
        "anchor": anchor,
        "scenes": out_scenes,
        "scene_timings": scene_timings,
    }
