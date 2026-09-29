"""Backtest — pichle candles par strategy (paper only, koi live nahi).

Tareeka: har band 5m candle par HTF(1h) rukh → signal → paper journal.
Seedha jawab: kitne trades, kitne jeete, net R.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.signal import generate_signal, htf_bias  # noqa: E402
from market.binance import Candle, fetch_klines  # noqa: E402
from market.validator import validate_candles  # noqa: E402
from paper.journal import Engine  # noqa: E402

SYMBOL, LTF, HTF = "BTCUSDT", "5m", "1h"
TF_MS = {"5m": 5 * 60 * 1000}
BARS = 3000


def _fetch_all(symbol: str, interval: str, bars: int) -> list[Candle]:
    """5000 se kam bhi mile to jo mila usi par (throttle-safe, ek call per batch)."""
    import requests
    from market.binance import BASE_URL

    all_rows: list = []
    end = None
    while len(all_rows) < bars:
        params = {"symbol": symbol, "interval": interval, "limit": min(1000, bars - len(all_rows))}
        if end:
            params["endTime"] = end
        r = requests.get(f"{BASE_URL}/fapi/v1/klines", params=params, timeout=20)
        if r.status_code != 200:
            raise RuntimeError(f"Binance HTTP {r.status_code}")
        batch = r.json()
        if not batch:
            break
        all_rows = batch + all_rows
        end = batch[0][0] - 1
        if len(batch) < 1000:
            break
        time.sleep(0.3)
    out = [
        Candle(time=int(x[0]), open=float(x[1]), high=float(x[2]), low=float(x[3]), close=float(x[4]), volume=float(x[5]))
        for x in all_rows[-bars:]
    ]
    return sorted(out, key=lambda c: c.time)


def main() -> None:
    print(f"data la raha hu ({SYMBOL} {LTF} x{BARS})...", flush=True)
    ltf = _fetch_all(SYMBOL, LTF, BARS)[:-1]
    htf = _fetch_all(SYMBOL, HTF, 500)[:-1]
    v = validate_candles(ltf, TF_MS[LTF])
    print(f"candles: {len(ltf)}, valid={v.valid} score={v.score}", flush=True)
    if not v.valid:
        print("ganda data, ruko:", v.errors[:3])
        return
    eng = Engine()
    htf_idx = 0
    t0 = time.time()
    for i in range(40, len(ltf)):
        while htf_idx + 1 < len(htf) and htf[htf_idx + 1].time <= ltf[i].time:
            htf_idx += 1
        bias = htf_bias(htf[: htf_idx + 1], htf_idx)
        sig = generate_signal(ltf[: i + 1], i, bias=bias)
        if sig:
            eng.queue(sig, LTF)
        eng.on_candle(LTF, ltf[i], TF_MS[LTF])
        if i % 500 == 0:
            print(f"  ...{i}/{len(ltf)} ({len(eng.closed)} band)", flush=True)
    s = eng.summary()
    rs = [t.r_multiple for t in eng.closed]
    print("---- RESULT ----")
    print(f"trades: {s['closed']} | wins: {s['wins']} | win_rate: {s['win_rate']}%")
    print(f"net R: {round(sum(rs), 2)} | avg R: {round(sum(rs) / len(rs), 2) if rs else 0}")
    print(f"equity: ${s['equity']} (start $10000)")
    print(f"time: {round(time.time() - t0, 1)}s")


if __name__ == "__main__":
    main()
