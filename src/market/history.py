"""History downloader — har timeframe ka 1 saal data, file me save (ek baar, phir roz thoda).

Hisab (1 saal):
  1d=365, 12h=730, 8h=1095, 6h=1460, 4h=2190, 2h=4380,
  1h=8760, 30m=17520, 15m=35040, 5m=105120, 3m=175200, 1m=525600 candles
Chote TF bhari hain (1m = 350 API calls) — dheere, ruk-ruk kar, file me save.
Dobara chalao to sirf NAYI candles judengi (purani dobara nahi).
"""
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE_URL = "https://fapi.binance.com"
SYMBOL = "BTCUSDT"
DATA_DIR = Path(__file__).resolve().parents[2] / "data"  # project/data (pehle src/data me gaya tha — fix)
DATA_DIR.mkdir(exist_ok=True)

YEAR_MS = 365 * 24 * 60 * 60 * 1000
TF_MS = {"1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
         "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000,
         "8h": 28_800_000, "12h": 43_200_000, "1d": 86_400_000}


def _file(tf: str) -> Path:
    return DATA_DIR / f"BTCUSDT_{tf}.json"


def _load(tf: str) -> list:
    f = _file(tf)
    if f.exists():
        try:
            return json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save(tf: str, rows: list) -> None:
    tmp = _file(tf).with_suffix(".tmp")
    tmp.write_text(json.dumps(rows))
    tmp.replace(_file(tf))


def download(tf: str) -> None:
    have = _load(tf)
    have_times = {r[0] for r in have} if have else set()
    since = (int(time.time() * 1000) - YEAR_MS) if not have else have[-1][0] + TF_MS[tf]
    print(f"[{tf}] have={len(have)}, downloading...", flush=True)
    end = (have[0][0] - 1) if have else None  # resume: sab se purani se peeche jao
    new = 0
    batches = 0
    while True:
        params = {"symbol": SYMBOL, "interval": tf, "limit": 1000}
        if end:
            params["endTime"] = end
        r = requests.get(f"{BASE_URL}/fapi/v1/klines", params=params, timeout=20)
        if r.status_code != 200:
            print(f"[{tf}] HTTP {r.status_code}, ruk kar retry...")
            time.sleep(10)
            continue
        batch = r.json()
        if not batch:
            break
        fresh = [row for row in batch if row[0] >= since and row[0] not in have_times]
        have = fresh + have if end else have + fresh
        new += len(fresh)
        batches += 1
        have_times.update(row[0] for row in fresh)
        end = batch[0][0] - 1
        if batches % 15 == 0:  # beech me save — tootne par dobara wahin se
            have.sort(key=lambda x: x[0])
            _save(tf, have)
            print(f"[{tf}] ...{len(have)} save (chal raha)", flush=True)
        if batch[0][0] < since or len(batch) < 1000:
            break
        time.sleep(0.4)  # Binance weight limit se bachao
    have.sort(key=lambda x: x[0])
    _save(tf, have)
    print(f"[{tf}] done: total={len(have)} (nayi {new})", flush=True)


if __name__ == "__main__":
    which = sys.argv[1:] or list(TF_MS)
    for tf in which:
        if tf not in TF_MS:
            print(f"unknown TF: {tf}")
            continue
        download(tf)
