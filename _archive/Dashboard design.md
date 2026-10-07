# Five Mark V1 — Dashboard Design (DeepCharts style)

> Status: LOCKED (29 Sep 2026, tumhara OK)
> Date: 29 Sep 2026
> Reference: deepcharts.com (orderflow / X-ray chart wala pro dashboard)
> Data source: `Five mark v1.md` (BTCUSDT, 1m to 1d, band candles only)

## 1. Ye dashboard kya hoga?

Ek **dark theme wala pro trader screen** — beech me bada chart, side me buy/sell seedhi (ladder),
neeche profit/loss ka hisaab. DeepCharts jaisa look: kaala background, hari/laal candles,
neele-grey boxes.

## 2. Colours (deepcharts.com se nikale hue — VERIFIED)

Site ka HTML khol kar nikale hain (guessing nahi):

| Cheez             | Colour code              | Matlab                    |
|-------------------|--------------------------|---------------------------|
| Background        | #030303 (bilkul kaala)   | Poori screen ka base      |
| Panel/box         | #1f1f1f + halki safed border | Cards, seedhi, P&L patti |
| Primary accent    | Purple #8b5cf6           | Buttons, active timeframe, headings |
| Candle up / Buy   | Hara #22c55e             | Price upar / kharid side  |
| Candle down / Sell| Laal #ef4444             | Price neeche / bech side  |
| Text/numbers      | Safed #f7f7f7            | Price, P&L                |
| Halka text        | Grey #8a8a8a             | Labels, headings          |
| Font              | Inter (bold headings)    | Poori site yehi font      |

> Source: deepcharts.com ka HTML (Framer site). Font Inter/Inter Display hai.

## 3. Screen layout (boxes)

```
+----------------------------------------------------------+
| TOP BAR: BTCUSDT | Live price | 1m...1d buttons | OK/ERROR |
+----------------------------------------------------------+
| ENGINE STATUS: abhi kya kar raha hai (jaise "5m scan,   |
| HTF UP, entry mili ▲" ya "WAIT — rukh saaf nahi")       |
+----------------------------------------------------------+
|                                                          |
|  BADA CHART (beech me, LIVE DRAWING) | SEEDHI (side)   |
|  - Candles (band only)               | - Buy / Sell    |
|  - ▲▼ entry nishan (live bante hain) | - 12 TF map     |
|  - Stop/Target lakeer (live)         |                 |
|  - FVG/OB zone box (halka rang)      |                 |
|                                                          |
+----------------------------------------------------------+
| NECHE PATTI: P&L | Open | Band | Seekhne wala box | Errors |
+----------------------------------------------------------+
```

## 4. Har box me kya dikhega? (data mapping)

| Box              | Data kahan se (`Five mark v1.md`)         |
|------------------|-------------------------------------------|
| Live price       | 1m ki last band close                     |
| Bada chart       | 12 timeframes ki band candles             |
| Signal nishan    | Signal Engine (agle design me)            |
| Stop/Target lakeer | Signal Engine (agle design me)          |
| Timeframe map    | 12 timeframes: hara = up, laal = down     |
| P&L patti        | Paper Trading (agle design me)            |
| OK/ERROR         | Quality check har timeframe ka            |
| Engine status    | Signal Engine ki live halat (scan/rukh/entry/WAIT) |
| Live drawing     | Entry ▲▼ + stop/target lakeer + FVG/OB box — signal bante hi chart par khud lagenge |

## 5. Rules (pakke)

1. **Live candle chart par nahi** — sirf band candles dikhengi.
2. **Drawing khud lagegi** — signal bante hi ▲▼ + stop/target + zone box chart par, haath se nahi.
3. **Refresh halka** — 3 second me ek baar screen update, API ko tang nahi.
4. **Galat data = laal ERROR** — chupana nahi, saaf dikhana hai.
5. **Engine chup nahi rahega** — har waqt status patti batayegi kya kar raha hai (scan? wait? entry?).
6. **Mobile baad me** — pehle computer screen, phone ka design baad me.

## 6. Agla step

* [x] Market data design LOCKED
* [x] Dashboard design LOCKED (29 Sep 2026)
* [ ] Notion page par dashboard section update
* [ ] Signal Engine design
* [ ] Paper Trading design
