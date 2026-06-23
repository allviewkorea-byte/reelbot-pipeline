"""SRT 자막 생성(#32) — suno 가사 타임코드 미제공 → 러프 동기화(가사 라인 균등 분배).

★ 0단계 조사 결과: sunoapi.org record-info 응답에 라인별 timed_lyrics 없음(id/audioUrl/
duration/title/tags 만). 따라서 가사 라인을 곡 구간([start_sec, start_sec+duration])에
**균등 분배**해 러프 동기화한다. mix JSON 의 tracks(각 start_sec + lyrics)를 활용.
"""

from __future__ import annotations


def _ts(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def generate_srt_from_tracks(tracks: list[dict], total_sec: float, lyrics_override: str | None = None) -> str:
    """mix tracks(각 start_sec + lyrics)로 SRT 생성. 라인을 곡 구간에 균등 분배(러프).

    lyrics_override: 번역본 전체 가사를 주면(라인 동일 가정) 그 텍스트로 대체(언어별 자막).
    """
    blocks: list[tuple[float, float, str]] = []
    valid = [t for t in (tracks or []) if (t.get("lyrics") or "").strip()]
    if lyrics_override and valid:
        # 번역본: 전체 라인을 전체 구간(첫 곡 시작~끝)에 균등 분배(라인 정렬 보장 X, 러프).
        all_lines = _lines(lyrics_override)
        start = float(valid[0].get("start_sec") or 0.0)
        span = max(1.0, total_sec - start)
        n = max(1, len(all_lines))
        per = span / n
        for i, ln in enumerate(all_lines):
            blocks.append((start + i * per, start + (i + 1) * per, ln))
    else:
        for idx, t in enumerate(valid):
            start = float(t.get("start_sec") or 0.0)
            nxt = (
                float(valid[idx + 1].get("start_sec"))
                if idx + 1 < len(valid) and valid[idx + 1].get("start_sec") is not None
                else total_sec
            )
            end = max(start + 1.0, nxt)
            lines = _lines(t.get("lyrics", ""))
            if not lines:
                continue
            per = (end - start) / len(lines)
            for i, ln in enumerate(lines):
                blocks.append((start + i * per, start + (i + 1) * per, ln))

    out: list[str] = []
    for i, (a, b, txt) in enumerate(blocks, 1):
        out.append(f"{i}\n{_ts(a)} --> {_ts(b)}\n{txt}\n")
    return "\n".join(out).strip() + ("\n" if out else "")


def build_srt_by_lang(tracks: list[dict], total_sec: float, lyrics_by_lang: dict[str, str]) -> dict[str, str]:
    """언어별 SRT — 원본 언어는 tracks 구간 동기화, 번역은 전체 분배(러프)."""
    result: dict[str, str] = {}
    # 원본(가장 정확): tracks 의 라인 단위 구간.
    base = generate_srt_from_tracks(tracks, total_sec)
    for lang, text in (lyrics_by_lang or {}).items():
        if not (text or "").strip():
            continue
        result[lang] = generate_srt_from_tracks(tracks, total_sec, lyrics_override=text)
    # 원본 언어 SRT 가 비어있지 않으면 우선순위로 둔다(라인 정렬 정확).
    if base.strip() and lyrics_by_lang:
        src = next(iter(lyrics_by_lang))
        result.setdefault(src, base)
    return result
