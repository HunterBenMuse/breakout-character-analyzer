# Worked Example — QQQ, Full History (Reference Study)

This is the analyzer's reference study: **QQQ** (Nasdaq-100 ETF), all five layers × both levels, run over the instrument's full available history. Every number below is quoted **verbatim from the study report**, including its margins and grades — including the cells that came out weak. That is what the tool's output looks like when the data is allowed to say "not enough."

## Bases

| Basis | Series | Span | Notes |
|---|---|---|---|
| QQQ-only | QQQ daily (Yahoo Finance, split-adjusted) | 1999-03-10 → 2026-11-20 | The instrument's whole life |
| Spliced | Nasdaq-100 index (^NDX) ratio-adjusted → QQQ | 1985-10-01 → 2026-11-20 | Pre-1999 segment is an **index proxy**, labelled as such wherever used |
| Yahoo hourly | QQQ 1h regular session (Yahoo) | 2023-12-27 → 2026-11-20 | Free hourly history is short — Yahoo serves ~730 days |
| Maxim37 hourly | 1-min bars from a public dataset, aggregated to hourly regular session | 2014-01-02 → 2024-01-10 | Split+dividend-adjusted basis; overlap-validated against Yahoo (close ratio median 1.00000, volume median ratio 1.000); never mixed with the Yahoo basis |

Weekly/monthly/yearly layers are aggregated from the daily series of each basis.

## Results — every cell

Walks: RSU = runs straight up · SP = shallow pullback · F = FALSE · M = MIXED. Success = RSU + SP. Failure median = median bars to the failure close, among failed events.

| Cell | n | Success | RSU | SP | F | M | Fail median |
|---|---|---|---|---|---|---|---|
| QQQ · HOURLY major (Yahoo) | 53 | 26.4% | 13 | 1 | 30 | 9 | 4.5 |
| QQQ · HOURLY small (Yahoo) | 45 | 17.8% | 8 | 0 | 27 | 10 | 7 |
| Maxim37 · HOURLY major | 172 | 25.0% | 36 | 7 | 109 | 20 | 8 |
| Maxim37 · HOURLY small | 154 | 25.3% | 32 | 7 | 98 | 17 | 8 |
| QQQ · DAILY major | 182 | 24.2% | 38 | 6 | 118 | 20 | 6.0 |
| QQQ · DAILY small | 122 | 28.7% | 29 | 6 | 78 | 9 | 5.5 |
| Spliced · DAILY major | 270 | 26.3% | 64 | 7 | 171 | 28 | 5 |
| Spliced · DAILY small | 194 | 30.9% | 51 | 9 | 111 | 23 | 6 |
| QQQ · WEEKLY major | 48 | 35.4% | 15 | 2 | 22 | 9 | 4.0 |
| QQQ · WEEKLY small | 27 | 48.1% | 12 | 1 | 8 | 6 | 5.0 |
| Spliced · WEEKLY major | 71 | 26.8% | 17 | 2 | 33 | 19 | 4 |
| Spliced · WEEKLY small | 43 | 48.8% | 20 | 1 | 13 | 9 | 6 |
| QQQ · MONTHLY major | 19 | 36.8% | 7 | 0 | 7 | 5 | 1 |
| QQQ · MONTHLY small | 4 | 50.0% | 2 | 0 | 1 | 1 | 8 |
| Spliced · MONTHLY major | 26 | 50.0% | 13 | 0 | 7 | 6 | 1 |
| Spliced · MONTHLY small | 6 | 33.3% | 2 | 0 | 3 | 1 | 3 |
| QQQ · YEARLY major | 11 | 45.5% | 4 | 1 | 2 | 4 | 1.5 |
| QQQ · YEARLY small | 10 | 50.0% | 4 | 1 | 2 | 3 | 1.5 |
| Spliced · YEARLY major | 23 | 52.2% | 11 | 1 | 3 | 8 | 2 |
| Spliced · YEARLY small | 12 | 41.7% | 4 | 1 | 2 | 5 | 1.5 |

## Sample-size block — every cell

Needed = events required at 95% confidence from the observed rate (worst case in brackets). Grade: within ±5 = **trustworthy** · within ±10 = **barely usable** · beyond ±10 = **trend only, never a rate**.

| Cell | Needed ±5 | Needed ±10 | In hand | Achieved | Grade |
|---|---|---|---|---|---|
| Yahoo HOURLY major | 299 [385] | 75 [97] | 53 | ±11.9 | trend only |
| Yahoo HOURLY small | 225 [385] | 57 [97] | 45 | ±11.2 | trend only |
| Maxim37 HOURLY major | 289 [385] | 73 [97] | 172 | ±6.5 | barely usable |
| Maxim37 HOURLY small | 291 [385] | 73 [97] | 154 | ±6.9 | barely usable |
| QQQ DAILY major | 282 [385] | 71 [97] | 182 | ±6.2 | barely usable |
| QQQ DAILY small | 315 [385] | 79 [97] | 122 | ±8.0 | barely usable |
| Spliced DAILY major | 298 [385] | 75 [97] | 270 | ±5.3 | barely usable |
| Spliced DAILY small | 329 [385] | 83 [97] | 194 | ±6.5 | barely usable |
| QQQ WEEKLY major | 352 [385] | 88 [97] | 48 | ±13.5 | trend only |
| QQQ WEEKLY small | 384 [385] | 96 [97] | 27 | ±18.8 | trend only |
| Spliced WEEKLY major | 302 [385] | 76 [97] | 71 | ±10.3 | trend only |
| Spliced WEEKLY small | 384 [385] | 96 [97] | 43 | ±14.9 | trend only |
| QQQ MONTHLY major | 358 [385] | 90 [97] | 19 | ±21.7 | trend only |
| QQQ MONTHLY small | 385 [385] | 97 [97] | 4 | ±49.0 | trend only |
| Spliced MONTHLY major | 385 [385] | 97 [97] | 26 | ±19.2 | trend only |
| Spliced MONTHLY small | 342 [385] | 86 [97] | 6 | ±37.7 | trend only |
| QQQ YEARLY major | 381 [385] | 96 [97] | 11 | ±29.4 | trend only |
| QQQ YEARLY small | 385 [385] | 97 [97] | 10 | ±31.0 | trend only |
| Spliced YEARLY major | 384 [385] | 96 [97] | 23 | ±20.4 | trend only |
| Spliced YEARLY small | 374 [385] | 94 [97] | 12 | ±27.9 | trend only |

## Bottom line — as the study stated it

- **Trustworthy (±5): no cell.** Nothing in this study may be quoted at ±5. The best cell (spliced daily majors, n = 270, ±5.3) stops 28 events short, and no more daily history for this instrument exists.
- **Barely usable (±10):** hourly on the Maxim37 basis (±6.5/±6.9) and daily on both bases (±5.3–±8.0). These four cells are the study's working numbers: **QQQ breakouts succeed roughly one time in four** (hourly ~25%, daily 24–31%), failure is the majority at both levels, shallow pullbacks are rare (≤7 per cell), and when failure comes it comes fast (median 5–8 bars).
- **Trend only:** everything weekly and slower, and the Yahoo-window hourly cells. The direction across layers is consistent in every basis and era cut: slower layers succeed more often, monthly/yearly around half — a tendency to respect, never a rate to trade on.
- The detector was verified three independent ways (predecessor reproduction, independent re-implementation, hand-graded regression set). The remaining unknowns are not in the arithmetic; they are the two data walls (daily history exhausted at 1985 via the index splice; free hourly history ending in 2014 on the long basis).

## Reproducing it

With data equivalent to the bases above (daily series from 1999, or a ratio-adjusted index splice from 1985; hourly regular-session bars), the release program reproduces every cell:

```bash
python3 breakout_character_analyzer.py --input daily_qqq_1999-2026.csv \
    --timeframe daily --out ./qqq-only
python3 breakout_character_analyzer.py --input daily_spliced_1985-2026.csv \
    --timeframe daily --out ./spliced
python3 breakout_character_analyzer.py --input hourly_qqq.csv \
    --timeframe hourly --layers HOURLY --context daily_qqq_1999-2026.csv \
    --out ./hourly
```

This generalized release was itself validated by exactly these runs: all 20 cells match the study report above — event counts, success rates, and achieved margins — with no differences.
