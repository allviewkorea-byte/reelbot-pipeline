"""
API 비용 추적 및 예상 비용 출력.
모든 단가는 USD 기준이며 참고용 근사치다.
"""

from dataclasses import dataclass, field

# ── 단가 (USD) ────────────────────────────────────────────────────
PRICE = {
    "gpt_image":    0.04,    # gpt-image-1 high quality / 장
    "street_view":  0.007,   # Google Street View Static API / 회
    "kie_clip_10s": 0.14,    # KIE (Kling) std 10초 클립 / 개
    "claude":       0.02,    # Claude opus narration 1회 (근사)
    "edge_tts":     0.00,    # Edge TTS 무료
}

KRW_RATE = 1_350  # USD → KRW 환율 (참고용)


@dataclass
class CostTracker:
    gpt_images: int = 0
    street_views: int = 0
    kie_clips: int = 0
    claude_calls: int = 0

    def add_image(self):       self.gpt_images += 1
    def add_streetview(self):  self.street_views += 1
    def add_kie_clip(self):    self.kie_clips += 1
    def add_claude(self):      self.claude_calls += 1

    @property
    def total_usd(self) -> float:
        return (
            self.gpt_images   * PRICE["gpt_image"]
            + self.street_views * PRICE["street_view"]
            + self.kie_clips    * PRICE["kie_clip_10s"]
            + self.claude_calls * PRICE["claude"]
        )

    def print_summary(self, label: str = "실제 비용"):
        _print_table(
            label=label,
            rows=[
                ("GPT-4o 이미지", self.gpt_images,   "장", PRICE["gpt_image"]),
                ("Street View",   self.street_views,  "회", PRICE["street_view"]),
                ("KIE 클립",      self.kie_clips,     "개", PRICE["kie_clip_10s"]),
                ("Claude API",    self.claude_calls,  "회", PRICE["claude"]),
            ],
            total=self.total_usd,
        )


def _print_table(label: str, rows: list, total: float):
    bar = "─" * 52
    print(f"\n  ┌{bar}┐")
    print(f"  │  {label:<50}│")
    print(f"  ├{bar}┤")
    for name, count, unit, unit_price in rows:
        subtotal = count * unit_price
        free = "(무료)" if unit_price == 0 else f"${subtotal:.3f}"
        print(f"  │  {name:<14} {count:>3}{unit} × ${unit_price:.3f} = {free:<10}│")
    print(f"  ├{bar}┤")
    print(f"  │  {'합계':<14}  ${total:.3f}  ≈  ₩{int(total * KRW_RATE):>8,}         │")
    print(f"  └{bar}┘")


def estimate(
    num_spots: int,
    seedance_scene_count: int,
    seedance_mode: str,
    seed_images: int = 3,
) -> CostTracker:
    """파이프라인 실행 전 예상 비용 계산 → CostTracker 반환."""
    t = CostTracker()
    t.gpt_images   = seed_images + num_spots   # 시드 3장 + 관광지별 1장
    t.street_views = num_spots
    t.kie_clips    = seedance_scene_count if seedance_mode == "kie" else 0
    t.claude_calls = 1
    return t


def print_cost_estimate(config, num_spots: int, seedance_scene_count: int):
    """영상 생성 직전 예상 비용을 출력한다."""
    from manual_brief import _seedance_scene_count
    t = estimate(
        num_spots=num_spots,
        seedance_scene_count=seedance_scene_count,
        seedance_mode=config.seedance_mode,
    )
    t.print_summary(label="예상 비용 (참고용)")
