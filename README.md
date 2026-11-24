# Breakout Character Analyzer

**One question, answered honestly for any ticker: when this instrument breaks above a meaningful prior high, what usually happens next — and how much should you trust that answer?**

Most published breakout statistics are pooled across thousands of stocks: one success rate for a pattern, as if every instrument behaved the same. They don't. This tool measures breakout behaviour **per instrument**: it finds the breakouts in one ticker's own history, classifies what price did after each one, and reports the statistics **with their sample sizes and margins of error attached**. A rate without its *n* and its ± is not a result, and this tool never prints one.

Pure Python 3, standard library only. No API key. Bring your own OHLCV data as a CSV, or fetch a ticker from Yahoo Finance's free chart API.

---

## Quick start

```bash
# 1. Smoke-test on the bundled sample (QQQ daily bars, 2018–2021):
python3 breakout_character_analyzer.py \
    --input examples/qqq_daily_2018-2021.csv --timeframe daily \
    --layers DAILY --out ./results --report ./results/report.md

# 2. Full character run on any ticker (fetches from Yahoo Finance):
python3 breakout_character_analyzer.py --symbol SPY --timeframe daily

# 3. Hourly layer (Yahoo serves at most ~730 days of hourly bars):
python3 breakout_character_analyzer.py --symbol QQQ --timeframe hourly --layers HOURLY
```

Outputs land in `--out`: `events.json` / `events.csv` (every breakout, fully described) and `stats.json` (the statistics, with the sample-size block). `--report` additionally writes a Markdown report like the one in [EXAMPLE-QQQ.md](EXAMPLE-QQQ.md).

---

## What it measures

For each of up to five time layers (**hourly, daily, weekly, monthly, yearly**) and two significance levels (**major** and **small** points), the analyzer:

1. **Finds meaningful prior highs** — swing highs *formed* over several bars (a one-candle spike tip never counts), which are either **historic** (highest of the lookback) or **formed with volume** (formation volume clearly above the base median). Formed highs that are neither are **small** points.
2. **Detects breakout events** — the first close above such a point. One candle breaking several points is one event.
3. **Grades the breakout candle** — STANDARD / PARTIAL / WEAK, from its effective length (body *plus* any gap-up segment) against the rolling median body, and its volume against two baselines: the trailing 20-bar average, and the quiet pullback bars immediately before the break.
4. **Classifies the walk** — what price did next, over a fixed follow window:
   - **RUNS STRAIGHT UP** — pullback no deeper than ⅓ of the breakout candle's span;
   - **SHALLOW PULLBACK** — pullback between ⅓ and ½, on non-enlarged volume, then continuation;
   - **FALSE** — a close below the breakout candle's low, or a deep pullback on enlarged volume that gives the break back;
   - **MIXED** — everything else.
   **Success** = runs straight up + shallow pullback.
5. **Reports the statistics with their credibility attached** (below).

Every event also records: the two volume ratios, pullback depth (lows- and closes-based), maximum advance, bars to failure, whether price threw back to the broken level, an ATR(14) race (+1 ATR before −1 ATR), the market regime tag, and honesty flags (e.g. `window_edge_artifact` for small points whose formation volume could not be evaluated at the edge of the data — the tool flags what it cannot know instead of guessing).

## The honesty rules (the point of the tool)

Every reported rate ships with a **sample-size block**:

| Field | Meaning |
|---|---|
| `needed_pm5` / `needed_pm10` | events required for a ±5 / ±10 percentage-point margin at 95% confidence, from the observed rate (worst case, at a 50% rate: 385 / 97) |
| `n` | events actually in hand |
| `achieved_pm` | the margin the data in hand actually carries |
| `grade` | **TRUSTWORTHY** (achieved ≤ ±5) · **BARELY USABLE** (≤ ±10) · **TREND ONLY** (> ±10 — a direction to respect, never a rate to trade on) |

Thin cells are labelled, never hidden or rounded into looking solid. If a cell has too little history, the tool says so — on real instruments, that happens a lot, and knowing it is worth more than a false precise number.

Two more rules are built in:

- **Events are not independent** (breakouts cluster in strong runs; the same physical top appears at several layers). Pooled figures are orientation, not measured rates, and the report says so.
- **The candle grade is descriptive.** In the reference study it did *not* separate success from failure — the separation was in the walk, above all the first retracement's depth and whether price ever closed below the breakout candle's low. The tool reports grades faithfully and lets the walk data speak.

## Inputs

- **CSV**: columns `date,o,h,l,c,v` (an extra leading `t` column is ignored). Dates: `YYYY-MM-DD` (daily) or `YYYY-MM-DD HH:MM` (hourly), interpreted as America/New_York. Weekly/monthly/yearly layers are aggregated from your daily (or hourly) input automatically.
- **`--symbol`**: fetches from Yahoo Finance's free chart API (daily: `--fetch-range`, default `10y`; hourly: fixed 730 days, Yahoo's maximum, regular-session bars only).
- **`--context daily.csv`** (optional): a longer daily series used *only* for regime tags, e.g. when the main input is hourly.
- **`--vol-ratio-pullback`** (default **1.2**): the pullback-relative volume threshold in the STANDARD grade. It touches grades only: in the reference study, moving it to 1.1 or 1.3 changed some daily STANDARD counts, left hourly grades almost unmoved, and changed **no event counts and no success rates** at any value. It is a parameter so you can verify that on your own instrument.

## Validation

The detection machinery was verified three independent ways in its reference study: (1) it reproduces every predecessor run event-for-event; (2) an independent re-implementation, written from the written definitions and sharing no code, re-derived the full event population (1,124 events, 20 cells) with zero discrepancies; (3) a hand-graded regression set (events graded by eye from charts before any program output was accepted) reproduces, including pullback depths to the third decimal. This generalized release reproduces all 20 cells of that study exactly — see [EXAMPLE-QQQ.md](EXAMPLE-QQQ.md).

## Limitations — stated, not buried

- **History is finite.** For a single instrument, slow layers (monthly/yearly) accumulate events so slowly that their cells stay TREND ONLY essentially forever; hourly history from free sources is short (Yahoo: ~730 days). The tool's grades make this visible instead of papering over it.
- **One instrument at a time, by design.** Character is per-instrument; pooling tickers would destroy the thing being measured. (Pooling is also the only road to ±5-grade cells — expect to need it if you want trustworthy slow-layer rates.)
- **Definitions are fixed and published** (in the program's header). A different definition of "meaningful high" or "failure" gives different numbers; the failure line used here is the breakout candle's low, and the reference study verified that the headline findings get *stronger*, not weaker, under a stricter line.
- This tool measures history. It does not predict, it does not place trades, and **it is not financial advice**.

## Licence

MIT — see [LICENSE](LICENSE). Commercial use is permitted under the licence. (A hosted, agent-callable version is a separate offering; the licence choice for this downloadable package is MIT.)
