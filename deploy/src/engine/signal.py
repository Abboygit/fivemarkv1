"""Signal Engine — Five-main ict-v2.ts ka Python copy + HTF→LTF gate (hamara modification).

Flow: HTF rukh (UP/DOWN/WAIT) → LTF entry sirf rukh wali side me.
Steps: sweep + displacement + FVG/OB + retrace + premium/discount veto + stop/target + RR>=2.5.
"""
import sys
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market.binance import Candle  # noqa: E402
from engine.primitives import atr, confirmed_swings, detect_fvg  # noqa: E402


def adx(candles: list[Candle], index: int, period: int = 14) -> float:
    """Calculate ADX at given index."""
    if index < period + 1:
        return 0.0
    
    tr_sum = 0.0
    plus_dm_sum = 0.0
    minus_dm_sum = 0.0
    
    for i in range(index - period + 1, index + 1):
        if i == 0:
            continue
        high = candles[i].high
        low = candles[i].low
        prev_close = candles[i - 1].close
        
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_sum += tr
        
        up_move = high - candles[i - 1].high
        down_move = candles[i - 1].low - low
        
        if up_move > down_move and up_move > 0:
            plus_dm_sum += up_move
        elif down_move > up_move and down_move > 0:
            minus_dm_sum += down_move
    
    if tr_sum == 0:
        return 0.0
    
    plus_di = 100 * (plus_dm_sum / tr_sum)
    minus_di = 100 * (minus_dm_sum / tr_sum)
    
    if plus_di + minus_di == 0:
        return 0.0
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    return dx

DISP_ATR = 0.5
DISP_RANGE_ATR = 0.8
RISK_REWARD = 3.0
PD_BUFFER = 0.08
LOOKBACK = 12
MIN_STOP_ATR_MULT = 1.0
MAX_STOP_ATR_MULT = 3.0

# Trailing stop configuration
TRAILING_STOP_ENABLED = True
TRAILING_STOP_ATR_MULT = 1.5  # Trail by 1.5x ATR
TRAILING_ACTIVATION_R = 1.5  # Activate trailing after 1.5R profit

# ICT Kill Zones (NY Time) - DISABLED by default, enable with USE_KILL_ZONES = True
KILL_ZONES = {
    "london": (2, 5),      # 2:00 - 5:00 AM NY
    "ny_am": (7, 10),      # 7:00 - 10:00 AM NY
    "silver_bullet": (10, 11),  # 10:00 - 11:00 AM NY (Silver Bullet)
}

# Sessions to avoid - DISABLED by default
AVOID_SESSIONS = {
    "ny_lunch": (12, 13),   # 12:00 - 13:00 PM NY (Lunch chop)
    "asian_range": (20, 24),  # 8 PM - 12 AM NY (Asian range accumulation)
}

# ICT Constants
OTE_FIB_LOW = 0.45   # Relaxed from 0.50 to 0.45
OTE_FIB_HIGH = 0.88  # Relaxed from 0.85 to 0.88
BREAKER_BUFFER = 0.001  # 0.1% buffer for breaker confirmation

# Filter Configuration (can be toggled)
VOLUME_FILTER_ENABLED = True
VOLUME_MULT = 1.5
SESSION_FILTER_ENABLED = True
ADX_FILTER_ENABLED = True
ADX_THRESHOLD = 10
USE_KILL_ZONES = True


@dataclass
class Signal:
    side: str  # "long" | "short"
    entry: float
    stop: float
    target: float
    rr: float
    reason: str
    event: str  # "fvg_retrace" | "ob_retrace" | "breaker_retrace" | "hidden_ob_retrace" | "bpr_retrace" | "silver_bullet" | "unicorn"
    index: int
    confidence: float
    zone_kind: str = ""  # "FVG" | "OB" | "BREAKER" | "HIDDEN_OB" | "BPR" (chart box ke liye)
    zone_high: float = 0.0
    zone_low: float = 0.0
    sweep_price: float = 0.0  # sweep point (chart dot ke liye)
    event_index: int = 0  # displacement wali candle (chart marker ke liye)


def _overlaps(c: Candle, low: float, high: float) -> bool:
    return c.low <= high and c.high >= low


def _displacement(candles: list[Candle], i: int) -> str | None:
    c = candles[i]
    a = atr(candles, i - 1) if i > 0 else 0.0
    if a <= 0:
        return None
    body, rng = abs(c.close - c.open), c.high - c.low
    if body < a * DISP_ATR or rng < a * DISP_RANGE_ATR:
        return None
    if c.close > c.open:
        return "bullish"
    if c.close < c.open:
        return "bearish"
    return None


def _sweep(candles: list[Candle], i: int) -> str | None:
    swings = confirmed_swings(candles, i)
    c, prev = candles[i], candles[i - 1] if i > 0 else None
    lows = [s for s in swings if s.side == "low" and s.index < i]
    highs = [s for s in swings if s.side == "high" and s.index < i]
    if lows and c.low < lows[-1].price and c.close > lows[-1].price and (prev is None or prev.low >= lows[-1].price):
        return {"direction": "bullish", "price": lows[-1].price}
    if highs and c.high > highs[-1].price and c.close < highs[-1].price and (prev is None or prev.high <= highs[-1].price):
        return {"direction": "bearish", "price": highs[-1].price}
    return None


SILVER_BULLET_LOOKBACK = 12  # 5m par ~1hr window — sweep displacement se pehle hona chahiye


def _sweep_before_displacement(candles: list[Candle], disp_i: int, direction: str, window: int = SILVER_BULLET_LOOKBACK):
    """Silver Bullet Step 1+2: sweep (Step 1) displacement (Step 2) se PEHLE hona chahiye.
    Sweep direction displacement direction se match karni chahiye (bullish disp =
    sell-side raid wala bullish sweep). Sirf full-pass candidates par chalao (rare)."""
    start = max(1, disp_i - window)
    for j in range(disp_i - 1, start - 1, -1):
        sw = _sweep(candles, j)
        if sw and sw.get("direction") == direction:
            return sw
    return None


def _mss_or_bos(candles: list[Candle], i: int, direction: str) -> bool:
    swings = confirmed_swings(candles, i)
    want = "high" if direction == "bullish" else "low"
    cands = [s for s in swings if s.side == want and s.index < i]
    if not cands:
        return False
    t = cands[-1]
    cur, prev = candles[i], candles[i - 1] if i > 0 else None
    if direction == "bullish":
        return cur.close > t.price and (prev is None or prev.close <= t.price)
    return cur.close < t.price and (prev is None or prev.close >= t.price)


def _fvg_zone(candles: list[Candle], disp_i: int, direction: str) -> dict | None:
    fvg_i = disp_i + 1
    if fvg_i >= len(candles) or detect_fvg(candles, fvg_i) != direction:
        return None
    first, third = candles[disp_i - 1], candles[fvg_i]
    if direction == "bullish":
        return {"kind": "FVG", "high": third.low, "low": first.high, "index": fvg_i}
    return {"kind": "FVG", "high": first.low, "low": third.high, "index": fvg_i}


def _ob_zone(candles: list[Candle], index: int, direction: str, lookback: int = 10) -> dict | None:
    for j in range(index - 1, max(-1, index - lookback) - 1, -1):
        c = candles[j]
        after = candles[j + 1 : index + 1]
        if not after:
            continue
        hi, lo = max(x.high for x in after), min(x.low for x in after)
        if direction == "bullish" and c.close < c.open and hi > c.high and candles[index].close > c.high:
            return {"kind": "OB", "high": c.open, "low": c.low, "index": j}
        if direction == "bearish" and c.close > c.open and lo < c.low and candles[index].close < c.low:
            return {"kind": "OB", "high": c.high, "low": c.open, "index": j}
    return None


def _premium_discount(price: float, hi: float, lo: float) -> str:
    n = (price - lo) / (hi - lo) if hi > lo else 0.5
    if n > 0.5 + PD_BUFFER:
        return "premium"
    if n < 0.5 - PD_BUFFER:
        return "discount"
    return "equilibrium"


def htf_bias(candles: list[Candle], index: int) -> str:
    """HTF rukh: UP / DOWN / WAIT. Primary trend (50-candle) has priority over structure."""
    # Primary trend: 50-candle direction (most reliable)
    primary_trend = "WAIT"
    if index >= 50:
        if candles[index].close > candles[index-49].close * 1.001:
            primary_trend = "UP"
        elif candles[index].close < candles[index-49].close * 0.999:
            primary_trend = "DOWN"

    # 50-candle SMA direction as secondary
    ma_short = 0
    ma_long = 0
    if index >= 50:
        ma_short = sum(c.close for c in candles[index-9:index+1]) / 10
        ma_long = sum(c.close for c in candles[index-49:index+1]) / 50

    # Structure check (only if aligns with primary trend)
    start = max(0, index - 59)
    window = candles[start : index + 1]
    hi = max(c.high for c in window)
    lo = min(c.low for c in window)
    pd = _premium_discount(candles[index].close, hi, lo)
    swings = confirmed_swings(candles, index)
    highs = [s.price for s in swings if s.side == "high"]
    lows = [s.price for s in swings if s.side == "low"]
    up = len(highs) >= 2 and len(lows) >= 2 and highs[-1] > highs[-2] and lows[-1] > lows[-2]
    dn = len(highs) >= 2 and len(lows) >= 2 and highs[-1] < highs[-2] and lows[-1] < lows[-2]

    # Structure must align with primary trend
    if primary_trend == "UP" and up:
        return "UP"
    if primary_trend == "DOWN" and dn:
        return "DOWN"
    # If no structure alignment, use primary trend
    if primary_trend != "WAIT":
        return primary_trend
    # SMA alignment as last resort
    if index >= 50:
        if ma_short > ma_long * 1.001 and pd != "premium":
            return "UP"
        if ma_short < ma_long * 0.999 and pd != "discount":
            return "DOWN"
    # NARM GATE: structure saaf na ho to aakhri 20 close ka rujhan dekho
    tail = candles[max(0, index - 20) : index + 1]
    if len(tail) >= 10:
        if tail[-1].close > tail[0].close * 1.002 and pd != "premium":
            return "UP"
        if tail[-1].close < tail[0].close * 0.998 and pd != "discount":
            return "DOWN"
    return "WAIT"


def pullback_pct(candles: list[Candle], index: int, lookback: int = 60) -> float:
    """HTF high se kitna neeche (0.015 = 1.5% pullback). Counter-trend trigger."""
    start = max(0, index - lookback + 1)
    window = candles[start : index + 1]
    if not window:
        return 0.0
    hi = max(c.high for c in window)
    if hi <= 0:
        return 0.0
    return (hi - candles[index].close) / hi


def generate_signal(candles: list[Candle], index: int, bias: str = "BOTH", check_kill_zone: bool = True) -> Signal | None:
    """LTF signal. bias=UP/DOWN/WAIT (HTF gate) ya BOTH (gate bandh, test ke liye).
    check_kill_zone: when False, skips kill zone and session filters (for HTF signals)."""
    if index < 30 or index >= len(candles):
        return None
    cur = candles[index]
    
    # ICT Kill Zone Filter - only trade during kill zones (skip for HTF signals)
    if check_kill_zone and USE_KILL_ZONES and not is_kill_zone(cur):
        return None
    
    # Avoid choppy sessions (skip for HTF signals)
    if check_kill_zone and SESSION_FILTER_ENABLED and is_avoid_session(cur):
        return None
    
    # Silver Bullet bonus (10-11 AM NY) - higher confidence
    is_sb = is_silver_bullet(cur)
    
    # Volume Filter - require volume > 1.5x average on displacement candle
    if VOLUME_FILTER_ENABLED:
        if index == 0:
            return None
        vol_avg = sum(c.volume for c in candles[max(0, index-20):index]) / min(20, index)
        if candles[index].volume < vol_avg * VOLUME_MULT:
            return None
    
    # ADX Filter - require ADX > threshold for trend strength
    if ADX_FILTER_ENABLED:
        if index < 20:
            return None
        adx_val = adx(candles, index)
        if adx_val < ADX_THRESHOLD:
            return None
    
    for ev in range(index, max(index - LOOKBACK, 0) - 1, -1):
        direction = _displacement(candles, ev)
        if not direction:
            continue
        sweep = _sweep(candles, ev)
        struct = _mss_or_bos(candles, ev, direction)
        if not sweep and not struct:
            continue
        
        # Check for multiple zone types in order of priority
        zone = None
        zone_type = ""
        
        # Priority 1: Breaker Block (highest probability)
        breaker = _breaker_block(candles, ev, direction)
        if breaker:
            # Unicorn check: Breaker ∩ FVG overlap = premium entry (do PD Array ek level par)
            # (FVG ko ev+1 candle chahiye — ev==index par future hota, isliye guard)
            fvg = _fvg_zone(candles, ev, direction) if ev < index else None
            if fvg:
                uni_low = max(breaker["low"], fvg["low"])
                uni_high = min(breaker["high"], fvg["high"])
                if uni_low < uni_high:
                    zone = {"kind": "UNICORN", "high": uni_high, "low": uni_low, "index": ev}
                    zone_type = "UNICORN"
                else:
                    zone = breaker
                    zone_type = "BREAKER"
            else:
                zone = breaker
                zone_type = "BREAKER"
        else:
            # Priority 2: Hidden OB (inside displacement)
            hidden = _hidden_ob(candles, ev, direction)
            if hidden:
                zone = hidden
                zone_type = "HIDDEN_OB"
            else:
                # Priority 3: BPR (Balanced Price Range)
                bpr = _balanced_price_range(candles, ev, direction)
                if bpr:
                    zone = bpr
                    zone_type = "BPR"
                else:
                    # Priority 4: Standard FVG/OB
                    # (FVG ko ev+1 candle chahiye — ev==index par future hota, isliye guard)
                    fvg_zone = _fvg_zone(candles, ev, direction) if ev < index else None
                    zone = fvg_zone or _ob_zone(candles, ev, direction)
                    if zone:
                        zone_type = zone["kind"]
        
        if not zone or zone.get("index", zone.get("index", 0)) >= index:
            continue
        if not _overlaps(cur, zone["low"], zone["high"]):
            continue
        
        side = "long" if direction == "bullish" else "short"
        if bias == "UP" and side != "long":
            continue
        if bias == "DOWN" and side != "short":
            continue
        if bias == "WAIT":
            return None
        start = max(0, index - 59)
        hi = max(c.high for c in candles[start : index + 1])
        lo = min(c.low for c in candles[start : index + 1])
        pd = _premium_discount(cur.close, hi, lo)
        if side == "long" and pd == "premium":
            continue
        if side == "short" and pd == "discount":
            continue
        
        # OTE (Optimal Trade Entry) - 62% to 79% Fib retracement
        swings = confirmed_swings(candles, index)
        swing_highs = [s for s in swings if s.side == "high" and s.index <= index]
        swing_lows = [s for s in swings if s.side == "low" and s.index <= index]
        
        if side == "long" and swing_highs and swing_lows:
            swing_high = swing_highs[-1].price
            swing_low = swing_lows[-1].price
            ote = _ote_zone(candles, index, "bullish", swing_high, swing_low)
            if not ote or not _overlaps(cur, ote["low"], ote["high"]):
                continue
        elif side == "short" and swing_highs and swing_lows:
            swing_high = swing_highs[-1].price
            swing_low = swing_lows[-1].price
            ote = _ote_zone(candles, index, "bearish", swing_high, swing_low)
            if not ote or not _overlaps(cur, ote["low"], ote["high"]):
                continue
        
        swings = confirmed_swings(candles, index)
        entry = cur.close
        if side == "long":
            stops = sorted([s.price for s in swings if s.side == "low" and s.price < entry], key=lambda p: entry - p)
            targets = sorted([s.price for s in swings if s.side == "high" and s.price > entry])
        else:
            stops = sorted([s.price for s in swings if s.side == "high" and s.price > entry], key=lambda p: p - entry)
            targets = sorted([s.price for s in swings if s.side == "low" and s.price < entry])
        if not stops or not targets:
            continue
        stop = stops[0]
        dist = abs(entry - stop)
        if not (entry * 0.0005 <= dist <= entry * 0.03):
            continue
        # Minimum stop distance based on ATR (1.5 * ATR)
        atr_val = atr(candles, index)
        if dist < atr_val * MIN_STOP_ATR_MULT:
            continue
        # Find first target that meets RR requirement
        target = None
        for t in targets:
            if abs(t - entry) >= dist * RISK_REWARD:
                target = t
                break
        if target is None:
            continue
        
        # Draw on Liquidity (DOL) - use liquidity pool as target if better
        dol_target = _draw_on_liquidity(candles, index, "UP" if side == "long" else "DOWN")
        if dol_target:
            if side == "long" and dol_target > target:
                target = dol_target
            elif side == "short" and dol_target < target:
                target = dol_target
        
        # Re-check RR with DOL target
        if abs(target - entry) < dist * RISK_REWARD:
            continue
        
        conf = 0.2 * bool(sweep) + 0.25 * bool(struct) + 0.25 + 0.2 + 0.1
        if zone_type == "UNICORN":
            conf = min(conf + 0.1, 1.0)  # Unicorn overlap bonus
        if is_silver_bullet(candles[index]):
            conf = min(conf + 0.1, 1.0)  # Silver Bullet window bonus
        reason = f"{'sweep+' if sweep else ''}{'mss/bos+' if struct else ''}displacement+{zone_type}+{pd}"

        # Determine event type based on zone type
        event_map = {
            "BREAKER": "breaker_retrace",
            "HIDDEN_OB": "hidden_ob_retrace",
            "BPR": "bpr_retrace",
            "FVG": "fvg_retrace",
            "OB": "ob_retrace",
            "HIDDEN_OB": "hidden_ob_retrace",
            "UNICORN": "unicorn",
        }
        event = event_map.get(zone_type, f"{zone_type.lower()}_retrace")

        # Silver Bullet 3-step: sweep (Step 1) displacement (Step 2) se pehle +
        # kill zone me FVG entry (Step 3) = premium "silver_bullet" event
        sb_sweep = None
        if check_kill_zone and USE_KILL_ZONES and is_kill_zone(cur):
            sb_sweep = _sweep_before_displacement(candles, ev, direction)
            if sb_sweep:
                event = "silver_bullet"
                conf = min(conf + 0.15, 1.0)
                reason = "SB:" + reason

        return Signal(
            side=side, entry=entry, stop=stop, target=target,
            rr=abs(target - entry) / dist, reason=reason,
            event=event, index=index, confidence=round(conf, 2),
            zone_kind=zone_type, zone_high=zone["high"], zone_low=zone["low"],
            sweep_price=(sweep["price"] if sweep else (sb_sweep["price"] if sb_sweep else 0.0)),
            event_index=ev,
        )
    return None


def find_zones(candles: list[Candle], end: int, lookback: int = 60) -> list[dict]:
    """Recent FVG/OB zones with status: active (fresh, untouched) | mitigated (touched, alive) | breaker (OB broken, flipped)."""
    out: list[dict] = []
    seen: set = set()
    for ev in range(max(1, end - lookback), end):
        direction = _displacement(candles, ev)
        if not direction:
            continue
        zone = _fvg_zone(candles, ev, direction) or _ob_zone(candles, ev + 2, direction)
        if not zone or zone["index"] in seen:
            continue
        seen.add(zone["index"])
        side = "long" if direction == "bullish" else "short"
        touched = any(
            _overlaps(candles[i], zone["low"], zone["high"])
            for i in range(zone["index"] + 1, end + 1)
        )
        fresh = zoneIsFresh(candles, zone, end, direction)
        if fresh:
            status = "mitigated" if touched else "active"
        elif zone["kind"] == "OB":
            status = "breaker"  # OB toot gaya — polarity flip
            side = "short" if side == "long" else "long"
        else:
            continue  # FVG dead
        out.append({"kind": zone["kind"], "status": status, "side": side,
                    "high": zone["high"], "low": zone["low"], "index": zone["index"]})
    return out[-8:]


def find_liquidity(candles: list[Candle], end: int) -> list[dict]:
    """Equal highs/lows (stop-hunt magnets): SSL neeche, BSL upar."""
    swings = confirmed_swings(candles, end)
    a = atr(candles, end) or 1.0
    tol = a * 0.15
    pools: list[dict] = []
    for side in ("high", "low"):
        pts = [x for x in swings if x.side == side][-12:]
        used: set = set()
        for i, p1 in enumerate(pts):
            if i in used:
                continue
            group = [p1]
            for j in range(i + 1, len(pts)):
                if abs(pts[j].price - p1.price) <= tol:
                    group.append(pts[j])
                    used.add(j)
            if len(group) >= 2:
                avg = sum(g.price for g in group) / len(group)
                pools.append({"side": "BSL" if side == "high" else "SSL",
                              "price": avg, "count": len(group), "index": group[-1].index})
    return sorted(pools, key=lambda x: x["count"], reverse=True)[:6]


def zoneIsFresh(candles: list[Candle], zone: dict, current: int, direction: str) -> bool:
    """TS zoneIsFresh ka Python copy (dict zone)."""
    if zone["high"] <= zone["low"]:
        return False
    for i in range(zone["index"] + 1, current):
        c = candles[i]
        if zone["kind"] == "FVG":
            bad = c.low <= zone["low"] if direction == "bullish" else c.high >= zone["high"]
        else:
            bad = c.close < zone["low"] if direction == "bullish" else c.close > zone["high"]
        if bad:
            return False
    return True


def is_kill_zone(candle: Candle) -> bool:
    """Check if candle timestamp falls within ICT kill zones (NY Time)."""
    dt = datetime.fromtimestamp(candle.time / 1000, tz=timezone.utc)
    # Convert to NY time (UTC-4 or UTC-5 depending on DST)
    # Simplified: assume UTC-4 (EDT) for now
    ny_hour = (dt.hour - 4) % 24
    
    # Check kill zones
    for zone_name, (start, end) in KILL_ZONES.items():
        if start <= ny_hour < end:
            return True
    return False


def is_avoid_session(candle: Candle) -> bool:
    """Check if candle falls in sessions to avoid (NY Lunch, Asian Range)."""
    dt = datetime.fromtimestamp(candle.time / 1000, tz=timezone.utc)
    ny_hour = (dt.hour - 4) % 24  # UTC to NY (EDT)
    
    for session_name, (start, end) in AVOID_SESSIONS.items():
        if start <= ny_hour < end:
            return True
    return False


def is_silver_bullet(candle: Candle) -> bool:
    """Check if candle is in Silver Bullet window (10-11 AM NY)."""
    dt = datetime.fromtimestamp(candle.time / 1000, tz=timezone.utc)
    ny_hour = (dt.hour - 4) % 24
    return 10 <= ny_hour < 11


def _breaker_block(candles: list[Candle], index: int, direction: str) -> dict | None:
    """Find Breaker Block - a failed OB that has flipped direction after being broken."""
    # Look for a broken OB in the opposite direction
    opposite_direction = "bearish" if direction == "bullish" else "bullish"
    
    # Look for OB in opposite direction that was broken
    for j in range(index - 1, max(-1, index - 20) - 1, -1):
        c = candles[j]
        if opposite_direction == "bullish":
            # Looking for bearish OB that was broken to the upside
            if c.close > c.open:  # bullish candle
                continue
            after = candles[j + 1:index + 1]
            if not after:
                continue
            hi = max(x.high for x in after)
            if hi > c.open + (c.open * BREAKER_BUFFER):  # Broken to upside
                return {"kind": "BREAKER", "high": c.open, "low": c.low, "index": j, "direction": "bullish"}
        else:
            # Looking for bullish OB that was broken to the downside
            if c.close < c.open:  # bearish candle
                continue
            after = candles[j + 1:index + 1]
            if not after:
                continue
            lo = min(x.low for x in after)
            if lo < c.open - (c.open * BREAKER_BUFFER):  # Broken to downside
                return {"kind": "BREAKER", "high": c.high, "low": c.open, "index": j, "direction": "bearish"}
    return None


def _hidden_ob(candles: list[Candle], index: int, direction: str) -> dict | None:
    """Hidden Order Block - forms inside a displacement candle."""
    if index < 2:
        return None
    
    disp_candle = candles[index]
    prev_candle = candles[index - 1]
    
    # Hidden OB forms inside the displacement candle
    if direction == "bullish":
        # Bullish displacement: look for bearish candle inside it
        if disp_candle.close > disp_candle.open:  # bullish displacement
            # Check if there's a small bearish candle inside
            if prev_candle.close < prev_candle.open:  # bearish candle
                return {"kind": "HIDDEN_OB", "high": prev_candle.open, "low": prev_candle.low, "index": index - 1}
    else:
        # Bearish displacement: look for bullish candle inside it
        if disp_candle.close < disp_candle.open:  # bearish displacement
            if prev_candle.close > prev_candle.open:  # bullish candle
                return {"kind": "HIDDEN_OB", "high": prev_candle.high, "low": prev_candle.open, "index": index - 1}
    return None


def _balanced_price_range(candles: list[Candle], index: int, direction: str) -> dict | None:
    """Balanced Price Range (BPR) - overlapping bullish and bearish FVGs."""
    # Look for overlapping bullish and bearish FVGs nearby
    for j in range(index - 1, max(-1, index - 10) - 1, -1):
        bullish_fvg = _fvg_zone(candles, j, "bullish")
        bearish_fvg = _fvg_zone(candles, j, "bearish")
        
        if bullish_fvg and bearish_fvg:
            # Check overlap
            overlap_low = max(bullish_fvg["low"], bearish_fvg["low"])
            overlap_high = min(bullish_fvg["high"], bearish_fvg["high"])
            
            if overlap_low < overlap_high:  # Overlap exists
                return {
                    "kind": "BPR",
                    "high": overlap_high,
                    "low": overlap_low,
                    "index": j,
                    "bullish_fvg": bullish_fvg,
                    "bearish_fvg": bearish_fvg
                }
    return None


def _ote_zone(candles: list[Candle], index: int, direction: str, swing_high: float, swing_low: float) -> dict | None:
    """Optimal Trade Entry (OTE) - 62% to 79% Fibonacci retracement zone."""
    if direction == "bullish":
        # Long: retrace from swing_high to swing_low
        fib_low = swing_high - (swing_high - swing_low) * OTE_FIB_HIGH  # 78.6%
        fib_high = swing_high - (swing_high - swing_low) * OTE_FIB_LOW   # 61.8%
    else:
        # Short: retrace from swing_low to swing_high
        fib_low = swing_low + (swing_high - swing_low) * OTE_FIB_LOW    # 61.8%
        fib_high = swing_low + (swing_high - swing_low) * OTE_FIB_HIGH  # 78.6%
    
    cur = candles[index]
    # Check if current price is in OTE zone
    if cur.low <= fib_high and cur.high >= fib_low:
        return {"kind": "OTE", "high": fib_high, "low": fib_low, "index": index}
    return None


def _draw_on_liquidity(candles: list[Candle], index: int, bias: str) -> float | None:
    """Draw on Liquidity (DOL) - target liquidity pool price is drawn to."""
    swings = confirmed_swings(candles, index)
    if bias == "UP" or bias == "DOWN":
        # Find relevant liquidity pool in direction of bias
        if bias == "UP":
            # Target BSL (buy-side liquidity above)
            highs = [s for s in swings if s.side == "high" and s.index <= index]
            if highs:
                return highs[-1].price  # Most recent swing high
        else:
            # Target SSL (sell-side liquidity below)
            lows = [s for s in swings if s.side == "low" and s.index <= index]
            if lows:
                return lows[-1].price  # Most recent swing low
    return None


def is_kill_zone_or_silver_bullet(candle: Candle) -> bool:
    """Check if candle is in any kill zone or silver bullet window."""
    return is_kill_zone(candle) or is_silver_bullet(candle)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from market.binance import fetch_klines

    htf = fetch_klines("BTCUSDT", "1h", 120)[:-1]  # band only (aakhri chalti bahar)
    ltf = fetch_klines("BTCUSDT", "5m", 120)[:-1]
    bias = htf_bias(htf, len(htf) - 1)
    print(f"HTF(1h) rukh: {bias}")
    sig = generate_signal(ltf, len(ltf) - 1, bias=bias)
    print(f"LTF(5m) signal: {sig}")
