"""Market data reader — Binance Futures public klines (key nahi chahiye).

Design: Five mark v1.md (BTCUSDT, 1m to 1d, band candles only).
Skill used: api-connector-builder (repo-native layers: transport + mapping).
"""
from dataclasses import dataclass

import requests

BASE_URL = "https://fapi.binance.com"


@dataclass
class Candle:
    """Ek band candle: time (ms), OHLC, volume."""

    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def fetch_klines(symbol: str = "BTCUSDT", interval: str = "5m", limit: int = 10) -> list[Candle]:
    """Binance se candles lao. Sirf check ke liye — live trade nahi."""
    if not 1 <= limit <= 1500:
        raise ValueError("limit 1..1500 ke beech hona chahiye")
    url = f"{BASE_URL}/fapi/v1/klines"
    resp = requests.get(url, params={"symbol": symbol.upper(), "interval": interval, "limit": limit}, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Binance error: HTTP {resp.status_code}")
    rows = resp.json()
    if not isinstance(rows, list):
        raise RuntimeError("Binance se galat jawab aaya")
    candles = []
    for row in rows:
        if len(row) < 6:
            raise RuntimeError("Adhoori candle mili, chori")
        candles.append(
            Candle(
                time=int(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
        )
    return candles


if __name__ == "__main__":
    for c in fetch_klines():
        print(f"{c.time} O={c.open} H={c.high} L={c.low} C={c.close} V={c.volume}")
