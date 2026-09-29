# Five Mark V1 — Paper Trading Design (nakli paise, asli hisaab)

> Status: LOCKED (29 Sep 2026, tumhara OK)
> Date: 29 Sep 2026
> Base: Five-main wala paper-engine (reuse) — signal milne ke baad ka kaam
> Data: `Five mark v1.md` | Signal: `Signal Engine design.md` | Screen: `Dashboard design.md`

## 1. Paper trading kya hai? (seedha matlab)

**Nakli paise se asli jaisa trade.** Paisa nahi lagega, lekin hisaab bilkul asli jaisa:
fee kategi, slippage lagega, stop/target lagenge. Taaki jab strategy fail ho to
paisa nahi, sirf number haare.

## 2. Starting paisa (LOCKED suggestion)

| Cheez        | Faisla      | Wajah                          |
|--------------|-------------|--------------------------------|
| Starting     | $10,000 nakli | Bada enough, chota nahi       |
| Risk per trade | 1% ($100) | Ek trade me zyada na doobe     |
| Fee          | 0.04% har side | Binance jaisi asli fee        |
| Slippage     | 1 point     | Bhaav thoda hilta hai, wo gina |
| Max time     | 60 candles  | Atka trade time par band        |

## 3. Trade kaise hoga? (5 steps)

```
Signal mila (▲ BUY @ 65,080, STOP 64,950, TARGET 65,200)
   |
   v
1. WAIT — agli candle khulne ka intezar (signal wali par entry NAHI)
   |
   v
2. ENTRY — agli candle ke OPEN par nakli entry + fee/slippage kaat kar
   quantity = $100 risk / (entry − stop) distance
   |
   v
3. NIGRANI — har band candle par check:
   - Target laga? → WIN, band (+2.5R)
   - Stop laga? → LOSS, band (−1R)
   - Dono ek hi candle me? → pehle STOP mana (safe side)
   - 60 candles ho gayin? → TIME-exit, jo bhaav ho
   |
   v
4. BAND — result + fee kaat kar final P&L
   |
   v
5. COPY — Seekhne wali copy me likha (Signal Engine 6B):
   setup, timeframe, HTF rukh, WIN/LOSS, R multiple
```

## 4. OPEN trades ke rules (ek sath kitne?)

* **Ek timeframe par ek trade** — 5m ka khula ho to 5m ka naya nahi
* **Alag timeframes chal sakte hain** — 5m + 15m + 1h ek sath OK
* **Max 5 open** — usse zyada hua to naya signal WAIT karega

## 5. Dashboard ko is se kya milega?

* Open trades list (entry, stop, target, abhi kitna up/down)
* Band trades history (jeeta/haara, R ke sath)
* P&L patti: aaj ka, total, win-rate %, max drawdown (sab se bada ghata)
* Seekhne wala box (Signal Engine wala)

## 6. Rules (pakke)

1. **Live paisa ZERO** — is file me live order ka zikr bhi ban hai.
2. **Signal candle par entry ban** — sirf agli candle ke open par.
3. **Fee/slippage hamesha** — munafa me se kaat kar dikhega, chupana nahi.
4. **Stop-first** — confusion ho to nuqsaan wali side mano (safe).
5. **Har trade copy me** — bina copy ke trade = hua hi nahi.

## 7. Five-main se kya lenge?

| Hissa (file)                  | Lena / Badalna                    |
|-------------------------------|-----------------------------------|
| `paper-engine.ts` (journal)   | LENA (jaise hai)                  |
| `execution.ts` (fee/slippage) | LENA (jaise hai)                  |
| Single-position backtest      | BADALNA (multi-timeframe open rakhenge) |
| Throw-on-bad-size             | BADALNA (skip + copy me note, crash nahi) |

## 8. Agla step (design phase ka hisaab)

* [x] Market data design LOCKED
* [x] Dashboard design LOCKED
* [x] Signal Engine design LOCKED (29 Sep 2026)
* [x] Paper Trading design LOCKED (29 Sep 2026)
* [ ] Notion page par baaki updates
* [ ] Phir BUILD phase (code likhna shuru)
