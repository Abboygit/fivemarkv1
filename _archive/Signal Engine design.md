# Five Mark V1 — Signal Engine Design (ICT + HTF→LTF)

> Status: LOCKED (29 Sep 2026, tumhara OK)
> Date: 29 Sep 2026
> Base: Five-main wala ICT V2 engine (reuse) + tumhara modification (HTF→LTF)
> Data: `Five mark v1.md` (BTCUSDT, 1m to 1d, band candles only)

## 1. Masla kya tha? (Five-main me kami)

Five-main me har timeframe **alag-alag** signal banata tha — 5m BUY bolta, 1h SELL bolta,
koi faisla nahi kaun sahi. Is liye tumne kaha: **HTF se LTF tak ek line me trade dekhna hai.**

## 2. Naya idea (top-down, ek line)

```
HTF (bada bhai: 1d, 4h, 1h)  →  RUKH batayega (up ya down)
              |
              v
MTF (darmiyan: 15m, 30m)     →  Rukh confirm karega
              |
              v
LTF (chota bhai: 5m, 3m, 1m) →  ENTRY dega (sirf HTF wali side me)
```

Seedha matlab: **bada bhai up bole tabhi chota bhai buy karega. Bada down bole to sirf sell.**

## 3. HTF rukh kaise niklega? (3 cheezen)

| Cheez            | Matlab (simple)                          |
|------------------|------------------------------------------|
| BOS/MSS          | Structure tootna = rukh badal sakta hai  |
| Premium/Discount | Mehenga (upar) = sell zone, Sasta (neeche) = buy zone |
| FVG/OB           | Wapsi wali jagah jahan price palat sakta hai |

* Rukh = UPa ya DOWN ya WAIT (saaf na ho to WAIT — zabardasti trade nahi)

## 4. LTF entry kaise hogi? (4 steps, sirf HTF wali side)

1. **Sweep** — choti timeframe par logon ka stop toota (jhansi wali move)
2. **Displacement** — tez body wali candle (bade paiso ka kadam)
3. **FVG/OB me wapsi** — price wapas zone me aaye
4. **Entry** — zone se palatne par, stop invalidation ke paar, target 2.5x (RR ≥ 2.5)

> Ye 4 steps Five-main ke engine me bane hue hain — copy karenge, naya nahi likhenge.

## 5. Five-main se kya lenge, kya badlenge?

| Hissa (file)              | Lena / Badalna                          |
|---------------------------|-----------------------------------------|
| `ict-primitives.ts` (ATR, swing, FVG) | LENA (jaise hai)              |
| `ict-v2.ts` (signal logic) | LENA + BADALNA (andar HTF rukh ka gate lagayenge) |
| `data-validator.ts`       | LENA (jaise hai)                        |
| Har-TF-alag loop          | BADALNA (HTF→MTF→LTF seedhi banayenge)  |
| `execution.ts` (fees/slippage) | LENA (jaise hai)                   |

## 6. Rules (pakke)

1. **HTF ke khilaf entry ban** — bada down, chota buy = NO trade.
2. **WAIT bhi faisla hai** — rukh saaf na ho to hath bandh ke baitho.
3. **Band candle only** — market data wali rule yahan bhi lagu.
4. **RR ≥ 2.5** — chota target wala trade nahi lenge.
5. **Seekhne ke liye paper only** — learning sirf nakli trades se, live par koi auto-change nahi.

## 6B. Self-learning — engine apne aap seekhega (DESIGN)

Seedha matlab: **har signal ka result likha jayega, aur jo setup jeetega uska number badhega.**

### Kya record hoga? (Seekhne ki copy)

Har band trade ke baad ye likha jayega:

| Cheez          | Example              |
|----------------|----------------------|
| Setup type     | FVG wala ya OB wala  |
| Timeframe      | 5m / 15m / 1h ...    |
| HTF rukh       | UP / DOWN (tab kya tha) |
| Result         | Win / Loss / Time-exit |
| R multiple     | +2.5 / −1.0 (kitna jeeta/haara) |

### Seekhna kaise hoga? (3 steps)

1. **Ginti** — har setup ka win-rate + average R niklega
   (jaise: FVG-5m = 60% win, OB-15m = 30% win)
2. **Number badlega** — jeetne wale setup ka confidence score upar,
   haarne wale ka neeche (khud, formula se — andaza nahi)
3. **Mashwara dega, faisla nahi** — engine kahega
   "OB-15m 30 trade me sirf 25% jeeta, band kar du?" —
   band TUM karoge, engine khud kuch band nahi karega

### Safety (dhoka na khaye)

* **30 trades se pehle koi faisla nahi** — choti ginti jhoot bolti hai
* **Paper par hi seekhega** — live paisa is se nahi judega
* **Purani seekh mitti nahi** — har hafte ka hisaab alag save, taaki pata rahe kab kya seekha

## 7. Dashboard ko is se kya milega?

* Har timeframe ka rukh (UP/DOWN/WAIT rang ke sath)
* LTF entry nishan + stop/target lakeer (mockup wala ▲▼)
* Rukh badalne par alert (Telegram baad me)
* Seekhne wala box: kaunsa setup kitna jeet raha (win-rate % + mashwara)

## 8. Agla step

* [x] Market data design LOCKED
* [x] Dashboard design LOCKED
* [x] Signal Engine design LOCKED (29 Sep 2026, HTF→LTF + self-learning)
* [x] Paper Trading design LOCKED (29 Sep 2026)
* [ ] Notion page par baaki updates
