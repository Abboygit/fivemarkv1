"""Pehla test — quality check (python-testing skill: simple, ek behavior)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from market.binance import Candle
from market.validator import validate_candles

TF_5M = 5 * 60 * 1000


def good_series() -> list[Candle]:
    base = 1_790_679_000_000
    return [
        Candle(time=base + i * TF_5M, open=100.0, high=101.0, low=99.0, close=100.5, volume=10.0)
        for i in range(5)
    ]


def test_clean_series_pass():
    r = validate_candles(good_series(), TF_5M)
    assert r.valid is True
    assert r.score == 100
    assert r.errors == []


def test_bad_ohlc_fail():
    bad = good_series()
    bad[2] = Candle(time=bad[2].time, open=100.0, high=50.0, low=99.0, close=100.5, volume=10.0)
    r = validate_candles(bad, TF_5M)
    assert r.valid is False
    assert any("OHLC" in e for e in r.errors)


def test_repeat_time_fail():
    bad = good_series()
    bad[3] = Candle(time=bad[2].time, open=100.0, high=101.0, low=99.0, close=100.5, volume=10.0)
    r = validate_candles(bad, TF_5M)
    assert r.valid is False
    assert any("repeat" in e for e in r.errors)


def test_gap_warn_only():
    series = good_series()
    series[4] = Candle(time=series[3].time + TF_5M * 5, open=100.0, high=101.0, low=99.0, close=100.5, volume=10.0)
    r = validate_candles(series, TF_5M)
    assert r.valid is True  # gap warning hai, fail nahi
    assert len(r.warnings) == 1
