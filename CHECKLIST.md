# Five Mark V1 — Master Checklist (bhoolne ke khilaf)

> Rule: har step se PEHLE isko parho, kaam ke BAAD tick karo.
> Ye file + Notion dono update honge. Yaad par kuch nahi chorega.

## Installs (ECC se)

* [x] Agents: planner, architect, code-architect, doc-updater
* [x] Agent: python-reviewer
* [x] Skills: python-patterns, python-testing, api-connector-builder, data-scraper-agent, dashboard-builder
* [x] Skill: frontend-patterns (dashboard Step 5 se pehle)
* [ ] HATAYA: chief-of-staff (email wala tha, kaam ka nahi)

## Designs (4/4 LOCKED)

* [x] Market data (BTCUSDT, 1m–1d)
* [x] Dashboard (DeepCharts style #030303/#8b5cf6/#22c55e)
* [x] Signal Engine (ICT + HTF→LTF + self-learning)
* [x] Paper Trading ($10k nakli)

## Build (4/5)

* [x] Step 1: data reader (live candles OK)
* [x] Step 2: quality check + 4 tests
* [x] Step 3: signal engine + 4 tests (10 signals/499 live proof)
* [x] Step 4: paper engine + 4 tests (12/12, 1 bug pakda+fix)
* [x] Step 5: dashboard (HTML, stdlib server :8090 — live OK, price+bias+paper)

## Safety (run se pehle, lazmi)

* [x] llm-trading-agent-security skill parhi + install (29 Sep 2026)
* [x] security-reviewer install + scan (29 Sep 2026): 0 secrets, 0 live-order, 1 GET (public klines only)
* [x] .gitignore banaya (venv/.env/logs bahar)
* [ ] Telegram token aaye tab .env me (git me nahi)

## Galti-log (dobara na ho)

1. chief-of-staff galat suggest kiya (email wala tha) — pehle parho, phir suggest karo
2. Mockup colours guess kiye — pehle source kholo, phir banao
3. frontend-patterns bhoola — ab se checklist se bahar kuch nahi
