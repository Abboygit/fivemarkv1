# Five Mark V1 — Market Data Design

> Status: DESIGN (code nahi, sirf kagaz)
> Date: 29 Sep 2026
> LOCKED: coin BTCUSDT + timeframes 1m se 1d tak (multi-timeframe)

## 1. Ye file kya hai?

Five Mark V1 bot ka pehla design — **market data kahan se aayega, kya aayega, kitni der me aayega.**
Dashboard isi data ko dikhayega, is liye data pehle fix hoga.

## 2. Data kahan se aayega?

* Source: **Binance Futures public API** (bina key ke, sirf candles)
* Endpoint: `GET /fapi/v1/klines?symbol=BTCUSDT&interval=<timeframe>&limit=251`
* Har timeframe alag se manga jayega (neeche list dekho)
* Kharcha: zero (public data, key nahi chahiye)

## 3. Kaunsa coin, kaunsa time?

| Cheez     | Faisla (LOCKED) | Wajah                          |
|-----------|-----------------|--------------------------------|
| Coin      | BTCUSDT         | Sab se zyada volume, data saaf |
| Timeframe | 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d (12 timeframes, chote se bade tak) | Choti move + badi trend dono dikhenge |
| Candles   | 251 per timeframe, ek baar me | Indicator ke liye pichla data chahiye |

> LOCKED by tumhara faisla (BTCUSDT, 1m to 1d). Change karna ho to batao.

## 4. Har candle me kya hoga?

| Field  | Matlab              | Example   |
|--------|---------------------|-----------|
| time   | Candle khulne ka time (ms) | 1727000000000 |
| open   | Khulne ka price     | 65000.5   |
| high   | Sab se uncha price  | 65100.0   |
| low    | Sab se neecha price | 64950.2   |
| close  | Band hone ka price  | 65080.0   |
| volume | Kitna maal ghuma    | 123.45    |

## 5. Flow diagram

```
Binance API (251 candles x 12 timeframes, BTCUSDT)
   |
   v
Quality check har timeframe par (time order me? OHLC sahi? gap to nahi?)
   |
   v
Sirf BAND candle use hogi (chalti hui candle kabhi nahi)
   |
   +-----> Signal Engine (agle step me design hoga)
   +-----> Paper Trading (agle step me design hoga)
   +-----> Dashboard (isi data ko dikhayega)
```

## 6. Rules (pakke)

1. **Chalti candle ban** — sirf band candle par faisla, kabhi live candle par nahi.
2. **Ek hi time dobara nahi** — jis candle ka time dekh liya, usko dobara process nahi (har timeframe alag track hoga).
3. **Ganda data = stop** — time ulta-seedha ya high<low mile to us timeframe ko choro, andha trade nahi.
4. **Chakkar timeframe ke hisab se** — 1m wala jaldi (15 sec), 1d wala der se (60 sec). Chote timeframe zyada, bade kam.

## 7. Dashboard ko is data se kya milega?

* Live price (1m ki last band close)
* 12 timeframes ka map (kaunsa up, kaunsa down — ek nazar me)
* Har timeframe ke candles ke points (chart ke liye)
* Data OK / ERROR status har timeframe ka (pata rahe data aa raha hai ya nahi)

## 8. Agla step

* [x] Coin + timeframe lock (BTCUSDT, 1m to 1d — LOCKED)
* [ ] Dashboard design shuru
* [ ] Notion page par ye sab update
