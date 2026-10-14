"""운동 채널 배경 이미지 자동화(PR-1) — 생성 · 자동 검수 · 렌더 정합 표식.

지금까지 운동 채널 배경은 대표가 폰 ChatGPT 로 만들어 "깨끗한 이미지 업로드"로 올렸다.
이 모듈은 그 손 단계를 대신한다.

  ① generate_reviewed  — GPT-Image-2.5 로 1장 생성 → Claude 비전으로 검수.
                         불합격이면 재생성 최대 1회, 그래도 불합격이면 이미지 없음(ok=False).
  ② attach_after_render — 렌더가 끝난 뒤 그 이미지를 대표 업로드와 **같은 자리**
                         (R2 music-thumbnails/{slug}/{mix_id}.png + thumbnail_r2_key)에 둔다.
                         그래야 재렌더·썸네일·검토대기 표시가 기존 경로를 그대로 탄다.
  ③ record_render / matching_render — "이 mp4 가 지금 배경으로 렌더된 것인가"를 R2
                         사이드카(music-videos/{slug}/{mix_id}_render.json)로 판정한다.
                         publish 가 재렌더를 건너뛸지 여기서 정한다. 애매하면 None(=재렌더).

★ 운동 채널 전용. where 는 이 모듈을 한 줄도 타지 않는다(호출부가 채널로 가른다).
★ music_video.py 무수정 — 이미지는 make_video(background_path=...) 로 바깥에서 넘긴다.
★ gpt-image-1 경로(music_video.generate_background 의 옛 코드)는 되살리지 않는다.

모델·사이즈·quality 는 env 로 덮을 수 있다. 기본값은 0단계에서 OpenAI 공식 도메인 검색으로
확인한 값이다(문서 원문 직접 열람은 네트워크 정책상 불가). 첫 실호출 로그가 확인 절차다.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 설정(env 로 덮기) ──────────────────────────────────────────────────
_DEFAULT_MODEL = "gpt-image-2.5-flare"
_DEFAULT_SIZE = "2048x1152"  # 16:9, 양 변 16의 배수, 2560x1440(실험 구간) 미만
_DEFAULT_QUALITY = "high"
# 이미지 출력 토큰 단가(USD / 1M) — 비용 추정 로그용. 공식 가격표가 바뀌면 env 로 덮는다.
_DEFAULT_OUTPUT_USD_PER_M = 30.0
_MAX_ATTEMPTS = 2  # 1회 + 불합격 시 재생성 최대 1회

# 검수용 축소본 — Claude 이미지 입력 한도(장당 5MB) 안에 넉넉히 들게 1024px JPEG 로.
_REVIEW_MAX_PX = 1024


def _env(key: str, default: str) -> str:
    return (os.getenv(key) or default).strip()


def image_model() -> str:
    return _env("MUSIC_IMAGE_MODEL", _DEFAULT_MODEL)


def image_size() -> str:
    return _env("MUSIC_IMAGE_SIZE", _DEFAULT_SIZE)


def image_quality() -> str:
    return _env("MUSIC_IMAGE_QUALITY", _DEFAULT_QUALITY)


def _output_usd_per_m() -> float:
    try:
        return float(_env("MUSIC_IMAGE_OUTPUT_USD_PER_M", str(_DEFAULT_OUTPUT_USD_PER_M)))
    except ValueError:
        return _DEFAULT_OUTPUT_USD_PER_M


def review_model() -> str:
    from config import CLAUDE_MODEL
    return _env("MUSIC_IMAGE_REVIEW_MODEL", CLAUDE_MODEL)


def wants_auto_image(channel: str | None, requested: bool | None) -> bool:
    """수동/라이브러리 생성에서 이미지 자동 생성을 할지. 운동 채널은 기본 ON(명시 False 만 끔).

    where(미지정 포함)는 무조건 False — 요청값과 무관하게 기존 동작 그대로.
    """
    from services.music_workout_style import is_workout_channel
    return is_workout_channel(channel) and requested is not False


# ── 프롬프트 ──────────────────────────────────────────────────────────
# API 전용 프리픽스 = 폰 ChatGPT 지침 공통 규칙 + 운동 톤(music_image_prompts.WORKOUT_TONE,
# 단일 정의) + 복사용 프리픽스엔 없던 항목("한 폭의 그림 같은 분위기", "보는 순간 몸을
# 움직이고 싶어지는 느낌", "현장감 허용·완벽하게 정돈하지 말 것").
# music_image_prompts 의 _WORKOUT_PREFIX·IMAGE_PROMPT_PREFIX 는 여기서 건드리지 않는다.
def api_prefix() -> str:
    from services.music_image_prompts import WORKOUT_TONE
    return (
        "실제 사진작가가 고급 카메라로 촬영한 가로 16:9 비율 사진. 한 폭의 그림 같은 분위기. "
        "고해상도, 선명하고 디테일이 풍부하게. AI가 만든 느낌 절대 없이. 텍스트, 글자, 워터마크 없이. "
        f"{WORKOUT_TONE} "
        "원판·덤벨·땀·트랙 등 현장감 있는 요소 허용. 완벽하게 정돈하지 말 것. "
        "보는 순간 몸을 움직이고 싶어지는 느낌."
    )


def build_prompt(action: str | None) -> str:
    """5단계 운동 풀(get_workout_image_prompt) + API 전용 프리픽스. [WORKOUT] 태그는 뗀다.

    [WORKOUT] 은 폰 ChatGPT 지침의 조건 분기용 표식이라 API 에는 의미가 없다.
    """
    from services import music_image_prompts as mip

    raw = mip.get_workout_image_prompt(action, include_prefix=False).strip()
    if raw.startswith(mip.WORKOUT_TAG):
        raw = raw[len(mip.WORKOUT_TAG):].strip()
    return f"{api_prefix()} {raw}".strip()


# ── 이미지 생성 ────────────────────────────────────────────────────────
def _usage_dict(resp) -> dict:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        try:
            return usage.model_dump()
        except Exception:  # noqa: BLE001
            pass
    return dict(usage) if isinstance(usage, dict) else {}


def _image_kind(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "unknown"


def _to_png(src: Path, dest: Path) -> None:
    """PNG 가 아니면 ffmpeg 로 PNG 변환(대표 업로드와 같은 .png·image/png 로 맞춘다)."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-frames:v", "1", str(dest)],
        check=True, capture_output=True, text=True,
    )


def generate_image(prompt: str, out_path: str) -> dict:
    """GPT-Image 1장 → out_path(PNG). 사용량·추정 비용 dict 반환. 실패 시 예외.

    응답은 b64_json / url 둘 다 처리한다(2.5 의 응답 형식은 문서 원문으로 확정하지 못했다).
    response_format 은 보내지 않는다(GPT Image 계열은 이 인자를 받지 않는 것으로 알려짐).
    """
    from openai import OpenAI
    import httpx

    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY 미설정 — 이미지를 생성할 수 없습니다.")
    model, size, quality = image_model(), image_size(), image_quality()
    client = OpenAI(api_key=key)
    resp = client.images.generate(model=model, prompt=prompt, size=size, quality=quality, n=1)
    data = getattr(resp, "data", None) or []
    if not data:
        raise RuntimeError("이미지 응답이 비어 있습니다.")
    item = data[0]
    b64 = getattr(item, "b64_json", None)
    url = getattr(item, "url", None)
    if b64:
        raw, fmt = base64.b64decode(b64), "b64_json"
    elif url:
        r = httpx.get(url, timeout=120.0, follow_redirects=True)
        r.raise_for_status()
        raw, fmt = r.content, "url"
    else:
        raise RuntimeError("이미지 응답에 b64_json/url 이 모두 없습니다.")

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    kind = _image_kind(raw)
    if kind == "png":
        out.write_bytes(raw)
    else:
        tmp = out.with_suffix(f".{kind if kind != 'unknown' else 'img'}")
        tmp.write_bytes(raw)
        _to_png(tmp, out)
        tmp.unlink(missing_ok=True)

    usage = _usage_dict(resp)
    out_tok = usage.get("output_tokens")
    in_tok = usage.get("input_tokens")
    est = round(out_tok * _output_usd_per_m() / 1_000_000, 4) if isinstance(out_tok, (int, float)) else None
    info = {
        "model": model, "size": size, "quality": quality, "response_format": fmt,
        "image_kind": kind, "bytes": len(raw),
        "output_tokens": out_tok, "input_tokens": in_tok, "est_output_usd": est,
    }
    # 첫 실호출 확인 절차 — 모델 ID·응답 형식·사용량이 이 한 줄에 다 찍힌다.
    logger.warning(
        "[auto-image] 생성 OK model=%s size=%s quality=%s format=%s kind=%s bytes=%d "
        "output_tokens=%s input_tokens=%s est_output_usd=%s usage=%s",
        model, size, quality, fmt, kind, len(raw), out_tok, in_tok, est, usage,
    )
    return info


# ── 자동 검수(Claude 비전) ─────────────────────────────────────────────
_REVIEW_SYSTEM = (
    "너는 운동·피트니스 유튜브 음악 채널의 배경 이미지 검수자다. 이 이미지는 영상 전체 배경과 "
    "썸네일로 그대로 쓰인다. 채널 톤은 '밝은 햇살 + 쨍한 원색 대비'다. "
    "아래 불합격 기준 중 하나라도 해당하면 불합격이다.\n"
    "1. 글자·숫자·로고·워터마크·간판 문구가 보인다(작고 흐릿해도 읽히면 해당).\n"
    "2. 정면 얼굴 클로즈업, 또는 화보·수영복처럼 몸매·노출을 강조한 인물.\n"
    "3. 손가락·팔다리·신체 기형, 또는 기구(바벨·덤벨·머신)가 물리적으로 어색하게 생겼다.\n"
    "4. 운동과 무관한 카페·거리·여행 풍경(헬스장·트랙·해변 러닝·스트레칭 같은 운동 장면이 아니다).\n"
    "5. 전체가 어둡거나 칙칙하다(야간·저조도·회색조·탁한 색감).\n"
    "6. 화면 중앙이 하얗게 날아가 있다 — 영상 중앙에 흰 로고가 올라가는데 안 보일 정도로 중앙이 "
    "희거나 과노출이면 불합격.\n"
    "실루엣·뒷모습 인물, 밝은 햇살, 선명한 그림자, 쨍한 원색은 정상이다. 애매하면 불합격으로 판단한다.\n"
    '반드시 JSON 한 개만 출력한다: {"pass": true 또는 false, "reasons": ["불합격 사유(한국어, 짧게)"]}. '
    "합격이면 reasons 는 빈 배열."
)


def _review_copy(src: str, dest: str) -> str:
    """검수용 축소 JPEG(가로 최대 1024px)."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", src, "-vf", f"scale='min({_REVIEW_MAX_PX},iw)':-2",
         "-frames:v", "1", "-q:v", "3", dest],
        check=True, capture_output=True, text=True,
    )
    return dest


def _parse_review(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        raise ValueError(f"검수 응답에 JSON 이 없습니다: {(text or '')[:120]}")
    obj = json.loads(m.group(0))
    passed = obj.get("pass")
    if not isinstance(passed, bool):
        raise ValueError(f"검수 응답의 pass 가 bool 이 아닙니다: {obj!r}"[:200])
    reasons = obj.get("reasons") or []
    if not isinstance(reasons, list):
        reasons = [str(reasons)]
    return {"pass": passed, "reasons": [str(r)[:120] for r in reasons][:5]}


def review_image(path: str) -> dict:
    """이미지 1장을 Claude 비전으로 검수 → {pass, reasons, model}. 호출·파싱 실패 시 예외."""
    from services import music_lyrics

    client = music_lyrics._client()
    tmpdir = Path(tempfile.mkdtemp(prefix="imgrev_"))
    try:
        small = _review_copy(path, str(tmpdir / "review.jpg"))
        b64 = base64.b64encode(Path(small).read_bytes()).decode("ascii")
        model = review_model()
        msg = client.messages.create(
            model=model,
            max_tokens=400,
            system=_REVIEW_SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                    {"type": "text", "text": "이 배경 이미지를 기준대로 검수하고 JSON 만 출력해."},
                ],
            }],
        )
        text = "".join(getattr(b, "text", "") for b in (msg.content or []))
        out = _parse_review(text)
        out["model"] = model
        return out
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def generate_reviewed(action: str | None, out_path: str) -> dict:
    """생성 → 검수. 불합격이면 재생성 최대 1회. {ok, path, attempts, summary}.

    API 오류·검수 실패(응답 파싱 불가 포함)도 그 시도의 불합격으로 친다 — 검수를 못 했으면
    쓰지 않는다. 어떤 경우에도 예외를 던지지 않는다(호출부는 ok 만 보면 된다).
    """
    out = Path(out_path)
    attempts: list[dict] = []
    for i in range(1, _MAX_ATTEMPTS + 1):
        rec: dict = {"attempt": i}
        cand = out.with_name(f"{out.stem}_try{i}.png")
        try:
            prompt = build_prompt(action)
            rec["prompt"] = prompt[:400]
            info = generate_image(prompt, str(cand))
            rec.update({k: info.get(k) for k in ("model", "output_tokens", "est_output_usd", "response_format")})
            review = review_image(str(cand))
            rec["pass"] = review["pass"]
            rec["reasons"] = review["reasons"]
            rec["review_model"] = review.get("model")
            logger.warning(
                "[auto-image] 검수 %s (시도 %d/%d) 사유=%s",
                "합격" if review["pass"] else "불합격", i, _MAX_ATTEMPTS, review["reasons"],
            )
            if review["pass"]:
                shutil.move(str(cand), str(out))
                attempts.append(rec)
                return {"ok": True, "path": str(out), "attempts": attempts, "summary": "합격"}
        except Exception as e:  # noqa: BLE001 - 시도 실패로 기록하고 다음 시도
            rec["pass"] = False
            rec["error"] = str(e)[:300]
            logger.warning("[auto-image] 시도 %d/%d 실패: %s", i, _MAX_ATTEMPTS, e)
        cand.unlink(missing_ok=True)
        attempts.append(rec)
    return {"ok": False, "path": None, "attempts": attempts, "summary": _fail_summary(attempts)}


def _fail_summary(attempts: list[dict]) -> str:
    bits = []
    for a in attempts:
        if a.get("error"):
            bits.append(f"{a['attempt']}차 오류: {a['error'][:80]}")
        else:
            bits.append(f"{a['attempt']}차 불합격: {', '.join(a.get('reasons') or ['사유 없음'])[:80]}")
    return " / ".join(bits) or "생성 실패"


def job_summary(res: dict) -> dict:
    """music_jobs.metadata·폴링 응답용 요약(프롬프트 원문은 짧게)."""
    return {
        "ok": bool(res.get("ok")),
        "summary": res.get("summary") or "",
        "attempts": [
            {k: a.get(k) for k in (
                "attempt", "pass", "reasons", "error", "model", "review_model",
                "output_tokens", "est_output_usd", "response_format", "prompt",
            ) if a.get(k) is not None}
            for a in (res.get("attempts") or [])
        ],
    }


# ── 렌더 정합 표식(publish 재렌더 건너뛰기 판정) ───────────────────────
_MARKER_VERSION = 1


def _marker_name(mix_id: str) -> str:
    return f"{mix_id}_render.json"


def _sha256(path: str | None) -> str | None:
    if not path or not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _design_hash() -> str:
    """make_video 가 읽는 것과 **같은 호출**(channel 미지정)의 디자인 설정 해시."""
    from services import music_channel
    cfg = music_channel.get_design_config()
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _norm_key(v) -> str | None:
    s = (v or "").strip() if isinstance(v, str) else ""
    return s or None


def record_render(
    slug: str, mix_id: str, *, bg_path: str, char_path: str | None, char_key: str | None,
    show_playlist: bool, vres: dict,
) -> bool:
    """렌더 직후 사이드카 기록. 첫프레임(=Remotion 렌더 성공)이 없으면 기록하지 않는다.

    best-effort — 실패하면 표식이 없을 뿐이고, 표식이 없으면 publish 는 재렌더한다(안전 쪽).
    """
    try:
        from adapters import r2_storage
        if not (vres.get("frame_thumb_key") and vres.get("video_url")):
            logger.info("[auto-image] 렌더 표식 생략(첫프레임 없음 = 폴백 렌더) mix_id=%s", mix_id)
            return False
        if not r2_storage.is_available():
            return False
        marker = {
            "v": _MARKER_VERSION,
            "mix_id": mix_id,
            "mp4_url": vres["video_url"],
            "frame_thumb_key": vres["frame_thumb_key"],
            "bg_sha256": _sha256(bg_path),
            "char_key": _norm_key(char_key),
            "char_sha256": _sha256(char_path) if char_path else None,
            "show_playlist": bool(show_playlist),
            "design_hash": _design_hash(),
        }
        if not marker["bg_sha256"]:
            return False
        tmpdir = Path(tempfile.mkdtemp(prefix="rmark_"))
        try:
            p = tmpdir / _marker_name(mix_id)
            p.write_text(json.dumps(marker, ensure_ascii=False), encoding="utf-8")
            r2_storage.upload_music_video(str(p), slug, _marker_name(mix_id), content_type="application/json")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        logger.info("[auto-image] 렌더 표식 기록 mix_id=%s bg=%s", mix_id, marker["bg_sha256"][:12])
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("[auto-image] 렌더 표식 기록 실패(publish 는 재렌더로 안전): %s", e)
        return False


def matching_render(row: dict, *, bg_path: str, char_path: str | None, show_playlist: bool) -> dict | None:
    """publish 직전 판정 — 현재 mp4 가 **지금 배경·인물·PLAY LIST·디자인**으로 렌더된 것인가.

    전부 일치할 때만 표식(dict, frame_thumb_key 포함)을 돌려준다. 하나라도 다르거나 표식이
    없거나 읽기/계산이 실패하면 None → 호출부는 재렌더한다(배경이 바뀌었는데 옛 mp4 가
    올라가는 사고가 최악이므로, 애매하면 항상 재렌더 쪽).
    """
    slug, mix_id = row.get("slug") or "", row.get("mix_id") or ""
    if not (slug and mix_id):
        return None
    try:
        from adapters import r2_storage
        tmpdir = Path(tempfile.mkdtemp(prefix="rmatch_"))
        try:
            p = tmpdir / "marker.json"
            r2_storage.download_music_object(r2_storage.music_video_key(slug, _marker_name(mix_id)), str(p))
            marker = json.loads(p.read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception as e:  # noqa: BLE001 - 표식 없음/읽기 실패 → 재렌더
        logger.info("[auto-image] 렌더 표식 없음 → 재렌더 mix_id=%s (%s)", mix_id, str(e)[:120])
        return None

    try:
        row_char_key = _norm_key(row.get("character_r2_key"))
        checks = {
            "version": marker.get("v") == _MARKER_VERSION,
            "mix_id": marker.get("mix_id") == mix_id,
            "mp4_url": bool(row.get("mp4_url")) and marker.get("mp4_url") == row.get("mp4_url"),
            "frame": bool(marker.get("frame_thumb_key")),
            "bg": bool(marker.get("bg_sha256")) and marker.get("bg_sha256") == _sha256(bg_path),
            "char_key": marker.get("char_key") == row_char_key,
            # 인물 키가 있는데 파일을 못 받았으면(char_path None) 불일치로 본다.
            "char": (marker.get("char_sha256") == (_sha256(char_path) if char_path else None))
                     and not (row_char_key and not char_path),
            "show_playlist": marker.get("show_playlist") is bool(show_playlist),
            "design": marker.get("design_hash") == _design_hash(),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("[auto-image] 렌더 정합 판정 실패 → 재렌더 mix_id=%s: %s", mix_id, e)
        return None
    failed = [k for k, ok in checks.items() if not ok]
    if failed:
        logger.warning("[auto-image] 렌더 정합 불일치 → 재렌더 mix_id=%s 불일치=%s", mix_id, ",".join(failed))
        return None
    logger.warning("[auto-image] 렌더 정합 일치 → publish 재렌더 생략 mix_id=%s", mix_id)
    return marker


def prepare_for_render(job_id: str, action: str | None, workdir: str) -> tuple[str | None, dict]:
    """렌더 직전 — 생성·검수 후 (배경 경로 또는 None, 요약). 요약은 music_jobs.metadata 에 남긴다.

    None 이면 호출부는 지금까지처럼 background_path 없이 렌더한다(블랙 배경, 반자동으로 떨어짐).
    """
    res = generate_reviewed(action, str(Path(workdir) / "auto_bg.png"))
    summary = job_summary(res)
    try:
        from services import music_jobs
        music_jobs.merge_metadata(job_id, {"auto_image": summary})
    except Exception:  # noqa: BLE001 - 추적 실패는 무시
        pass
    return (res["path"] if res.get("ok") else None), summary


def attach_after_render(slug: str, mix_id: str, bg_path: str, vres: dict) -> dict:
    """렌더 후 처리 — 이미지를 대표 업로드와 같은 자리에 두고(R2 + thumbnail_r2_key) 표식 기록.

    렌더 전에는 큐 행이 없어(record_pending 이 렌더 끝에 만든다) set_thumbnail 이 0행을 고친다.
    그래서 반드시 렌더 **뒤에** 부른다. {thumbnail_r2_key, error}.
    """
    from adapters import r2_storage
    from services import music_uploads

    try:
        r2_storage.upload_music_thumbnail(bg_path, slug, mix_id)
        key = r2_storage.music_thumbnail_key(slug, mix_id)
        res = music_uploads.set_thumbnail(mix_id, key)
        if res.get("error"):
            raise RuntimeError(res["error"])
    except Exception as e:  # noqa: BLE001 - 영상은 이미 만들어졌다(이미지 없이 검토대기)
        logger.warning("[auto-image] 썸네일 연결 실패 mix_id=%s: %s", mix_id, e)
        return {"thumbnail_r2_key": None, "error": str(e)[:300]}
    record_render(slug, mix_id, bg_path=bg_path, char_path=None, char_key=None, show_playlist=True, vres=vres)
    return {"thumbnail_r2_key": key, "error": None}
