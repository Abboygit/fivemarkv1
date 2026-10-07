"""Candle quality check — ganda data andar nahi aayega.

Design rules (Five mark v1.md):
1. Chalti candle ban (caller sirf band candles bheje).
2. Time order me hona chahiye, repeat nahi.
3. high >= sabse bada (open/close), low <= sabse chota.
4. Gap mile to warning (fail nahi — aage engine faisla karega).
"""
from dataclasses import dataclass, field

from .binance import Candle


@dataclass
class ValidationResult:
    valid: bool
    score: int  # 0..100
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_candles(candles: list[Candle], expected_ms: int) -> ValidationResult:
    """Poori series check karo. Ganda mile to valid=False + wajah."""
    errors: list[str] = []
    warnings: list[str] = []
    if not candles:
        return ValidationResult(valid=False, score=0, errors=["koi candle nahi mili"])

    prev_time = 0
    gaps = 0
    for i, c in enumerate(candles):
        if c.time <= 0:
            errors.append(f"candle {i}: time galat ({c.time})")
        for name in ("open", "high", "low", "close"):
            v = getattr(c, name)
            if not isinstance(v, float) or v != v or v in (float("inf"), float("-inf")) or v <= 0:
                errors.append(f"candle {i}: {name} galat ({v})")
        if c.volume < 0 or c.volume != c.volume:
            errors.append(f"candle {i}: volume galat ({c.volume})")
        if c.high < max(c.open, c.close) or c.low > min(c.open, c.close):
            errors.append(f"candle {i}: high/low OHLC se match nahi")
        if c.time <= prev_time:
            errors.append(f"candle {i}: time repeat/ulta ({c.time} <= {prev_time})")
        elif prev_time and c.time - prev_time > expected_ms * 1.5:
            gaps += 1
            warnings.append(f"candle {i}: gap mila ({(c.time - prev_time) // 1000}s)")
        prev_time = c.time

    score = max(0, 100 - len(errors) * 25 - gaps * 5)
    return ValidationResult(valid=not errors, score=score, errors=errors, warnings=warnings)
