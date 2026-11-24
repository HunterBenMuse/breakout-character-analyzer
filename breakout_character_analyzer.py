#!/usr/bin/env python3
"""
breakout_character_analyzer.py — Breakout Character Analyzer

WHAT IT DOES
------------
For one instrument (any ticker with OHLCV bars), this program measures the
instrument's breakout "character": how its price has historically behaved
after breaking above a meaningful prior high. It detects breakout events on
up to five time layers (hourly, daily, weekly, monthly, yearly), at two
levels of significance (MAJOR and SMALL points), grades each breakout
candle, classifies what price did next (the "walk"), and reports success
statistics in which EVERY rate is published together with its sample size
and its margin of error. A rate without its n and its +/- is not a result;
this tool never prints one.

DEFINITIONS (fixed; every parameter is named and listed in PARAMS below)
------------------------------------------------------------------------
MEANINGFUL PRIOR HIGH — a clear swing high at that layer, FORMED over
several bars (not a one-candle spike tip), that is either HISTORIC
(highest of the preceding lookback) or FORMED WITH VOLUME (formation-window
volume clearly above the layer's base/median volume). A point that is
formed but neither historic nor volume-formed is a SMALL point.
BREAKOUT EVENT — the first bar whose CLOSE exceeds a point not previously
broken by a close at that layer. One candle breaking several points is ONE
event; its grade follows the highest point broken.
CANDLE GRADE —
  STANDARD: a medium bullish candle whose effective length (body plus any
    gap-up segment, i.e. close vs the PRIOR close) is at least the layer's
    rolling median body of the prior 60 bars, WITH volume cooperation:
    trailing volume ratio >= 1.3, OR pullback-relative volume ratio
    >= VOL_RATIO_PULLBACK (default 1.2) with trailing ratio >= 1.0.
    (Two baselines are recorded because they answer different questions:
    the trailing ratio compares the breakout bar with the average recent
    bar; the pullback-relative ratio compares it with the quiet
    pullback/consolidation bars immediately before the break, which is how
    the move was actually launched.)
  PARTIAL: a medium bullish candle with only slightly enlarged volume, or
    strong volume on a short body.
  WEAK: everything else.
WALK — what price does after the break, followed until a bar CLOSES below
the breakout candle's low (mechanical failure) or the layer's follow
window ends. Pullback depth is measured over the FIRST RETRACEMENT
SEGMENT only (the bars after the breakout bar up to and including the
first close back above the breakout close, or the failure bar, or the
window end), as a fraction of the breakout candle's span (close - low).
Pullback volume is the MEDIAN volume of the segment bars vs the breakout
bar's volume. Classes:
  RUNS STRAIGHT UP   depth <= 1/3, no failure close.
  SHALLOW PULLBACK   1/3 < depth <= 1/2, pullback volume not enlarged,
                     and price continues (recovers or ends above the level).
  FALSE              a failure close; or depth > 1/2 WITH enlarged pullback
                     volume AND the break given back (window ends below
                     the broken level). Substance override: an event that
                     reached its next meaningful resistance or advanced
                     >= +10% inside the window, with no failure close, is
                     at most MIXED, never FALSE.
  MIXED              everything else.
SUCCESS = a true-side walk: RUNS STRAIGHT UP or SHALLOW PULLBACK (neither
ever closes below the breakout candle's bottom inside the window).
REGIME TAG (context only) — hourly/daily/weekly events are tagged from the
daily layer (last completed daily bar before the event): UPTREND = close
above a rising 200-day average; DOWNTREND = close below a falling one;
else SIDEWAYS. Monthly/yearly events use the monthly layer vs its
10-month average.

SAMPLE-SIZE BLOCK (attached to every reported rate)
---------------------------------------------------
needed_pm5 / needed_pm10 — events required for a +/-5 / +/-10 percentage
point margin at 95% confidence, computed from the observed rate (the
worst-case figures at a 50% rate are 385 and 97). achieved_pm — the margin
the data in hand actually carries. grade — TRUSTWORTHY (achieved <= 5),
BARELY USABLE (<= 10), or TREND ONLY (> 10: a direction to respect, never
a rate to trade on).

PARAMETER NOTE — VOL_RATIO_PULLBACK (default 1.2)
-------------------------------------------------
This threshold touches candle GRADES only. In the reference study behind
this tool (one instrument, full history, five layers, both levels), moving
it to 1.1 or 1.3 changed some daily STANDARD counts, left hourly grades
almost unmoved, and changed NO event counts and NO success rates at any
value. It is exposed as a parameter so you can verify that on your own
instrument instead of taking it on trust.

USAGE
-----
  # analyse a local CSV (columns: date,o,h,l,c,v — a leading t column is
  # ignored; dates are YYYY-MM-DD for daily, "YYYY-MM-DD HH:MM" for hourly,
  # interpreted as America/New_York):
  python3 breakout_character_analyzer.py --input bars.csv \
      --timeframe daily --layers DAILY,WEEKLY,MONTHLY,YEARLY \
      --levels major,small --out ./results

  # or fetch a ticker from Yahoo Finance (free chart API, no key):
  python3 breakout_character_analyzer.py --symbol QQQ --timeframe daily

Optional: --context daily.csv supplies a longer daily series used ONLY for
regime context (e.g. when the main input is hourly). --report FILE.md also
writes a Markdown report. --vol-ratio-pullback X overrides the 1.2 default.

Outputs in --out: events.json, events.csv, stats.json.
Pure Python 3 standard library; no third-party packages.
"""

import argparse, csv, json, math, sys, urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
Z95 = 1.96

VOL_RATIO_STANDARD = 1.3            # trailing-volume cooperation for STANDARD
VOL_RATIO_PARTIAL_FLOOR = 1.0       # bottom of the "slightly enlarged" band
PULLBACK_QUIET_MAX_BARS = 5         # how far back the quiet cluster may sit
SUBSTANCE_ADVANCE_PCT = 10.0        # substance override: >= this => at most MIXED
ATR_LEN = 14                        # ATR lookback for the recorded ATR race

# Per-layer detector parameters:
#   k             swing half-window (bars each side) for a "clear, obvious" top
#   formed_band   highs within this fraction of the top count as "at the top"
#   formed_span   half-window over which the formed structure is counted
#   formed_min    minimum bars near the top for a FORMED (not spike) top
#   hist_lookback bars of lookback for the HISTORIC-high test
#   vol_med_win   bars of base/median volume behind the formation window
#   vol_form_win  half-window around the top for formation volume
#   vol_thresh    formation volume must be >= this x base median
#   window        follow window (bars) for the post-breakout walk
#   seed_first    seed the series' first bar high as a HISTORIC point (use
#                 when the series opens on/near a known top whose formation
#                 lies before the series start); MAJOR level only
#   vol_ok        whether cross-bar volume ratios are meaningful at this layer
PARAMS = {
    "HOURLY":  dict(k=13, formed_band=0.007, formed_span=13, formed_min=5,
                    hist_lookback=1640, vol_med_win=250, vol_form_win=3,
                    vol_thresh=1.3, window=40, seed_first=False, vol_ok=True),
    "DAILY":   dict(k=5, formed_band=0.015, formed_span=5, formed_min=3,
                    hist_lookback=252, vol_med_win=60, vol_form_win=2,
                    vol_thresh=1.05, window=30, seed_first=True, vol_ok=True),
    "WEEKLY":  dict(k=3, formed_band=0.015, formed_span=4, formed_min=3,
                    hist_lookback=52, vol_med_win=26, vol_form_win=1,
                    vol_thresh=1.2, window=12, seed_first=True, vol_ok=True),
    "MONTHLY": dict(k=2, formed_band=0.015, formed_span=4, formed_min=3,
                    hist_lookback=12, vol_med_win=24, vol_form_win=1,
                    vol_thresh=1.2, window=8, seed_first=True, vol_ok=True),
    "YEARLY":  dict(k=0, formed_band=0.015, formed_span=1, formed_min=1,
                    hist_lookback=100, vol_med_win=3, vol_form_win=0,
                    vol_thresh=1.2, window=3, seed_first=True, vol_ok=False),
}
LAYER_ORDER = ["HOURLY", "DAILY", "WEEKLY", "MONTHLY", "YEARLY"]
# a layer can only be derived from a base timeframe at or below it
DERIVABLE = {"hourly": LAYER_ORDER,
             "daily": ["DAILY", "WEEKLY", "MONTHLY", "YEARLY"]}

# --------------------------------------------------------------------- utils
def median(xs):
    xs = sorted(xs); n = len(xs)
    return xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])

def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")

def sample_block(n, successes):
    """The honesty block attached to every rate: how many events a +/-5 and
    a +/-10 margin would need, and the margin the n in hand actually has."""
    if not n:
        return {"n": 0, "needed_pm5": None, "needed_pm10": None,
                "needed_pm5_worst": 385, "needed_pm10_worst": 97,
                "achieved_pm": None, "grade": "NO DATA"}
    p = successes / n
    if 0.0 < p < 1.0:
        var = p * (1 - p)
        needed5 = math.ceil(Z95 * Z95 * var / 0.05 ** 2)
        needed10 = math.ceil(Z95 * Z95 * var / 0.10 ** 2)
        achieved = Z95 * math.sqrt(var / n) * 100
    else:
        # a 0% or 100% observed rate: the normal margin collapses to 0,
        # which would be a false certainty — use the Wilson half-width for
        # the achieved margin and the worst-case (50% rate) requirements.
        needed5, needed10 = 385, 97
        z2 = Z95 * Z95
        denom = 1 + z2 / n
        centre = (p + z2 / (2 * n)) / denom
        half = Z95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
        achieved = half * 100
        _ = centre
    grade = ("TRUSTWORTHY" if achieved <= 5 else
             "BARELY USABLE" if achieved <= 10 else "TREND ONLY")
    return {"n": n, "needed_pm5": needed5, "needed_pm10": needed10,
            "needed_pm5_worst": 385, "needed_pm10_worst": 97,
            "achieved_pm": round(achieved, 1), "grade": grade}

# ------------------------------------------------------------------ data in
def parse_dt(s):
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=ET)
        except ValueError:
            continue
    raise ValueError(f"unrecognised date format: {s!r} "
                     "(expected YYYY-MM-DD or 'YYYY-MM-DD HH:MM')")

def read_csv_bars(path, timeframe):
    bars = []
    with open(path, newline="") as f:
        rdr = csv.DictReader(f)
        cols = {c.lower(): c for c in (rdr.fieldnames or [])}
        need = ["date", "o", "h", "l", "c", "v"]
        missing = [c for c in need if c not in cols]
        if missing:
            raise ValueError(f"{path}: missing columns {missing} "
                             f"(found {rdr.fieldnames})")
        for row in rdr:
            dt = parse_dt(row[cols["date"]])
            if timeframe == "daily":
                label = dt.strftime("%Y-%m-%d")
            else:
                label = dt.strftime("%Y-%m-%d %H:%M")
            bars.append({"dt": dt, "label": label,
                         "o": float(row[cols["o"]]), "h": float(row[cols["h"]]),
                         "l": float(row[cols["l"]]), "c": float(row[cols["c"]]),
                         "v": float(row[cols["v"]] or 0)})
    bars.sort(key=lambda b: b["dt"])
    return bars

def fetch_yahoo(symbol, rng, interval):
    """Free Yahoo Finance chart API (no key). Returns raw bars with labels
    unset; hourly bars are NOT session-filtered here (see main())."""
    last = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = (f"https://{host}/v8/finance/chart/{symbol}"
               f"?range={rng}&interval={interval}&includePrePost=false")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode())
            res = data["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            bars = []
            for i, t in enumerate(res["timestamp"]):
                if q["close"][i] is None:
                    continue
                bars.append({"dt": datetime.fromtimestamp(t, ET),
                             "o": float(q["open"][i]), "h": float(q["high"][i]),
                             "l": float(q["low"][i]), "c": float(q["close"][i]),
                             "v": float(q["volume"][i] or 0)})
            return bars
        except Exception as e:
            last = e
    raise RuntimeError(f"fetch failed {rng}/{interval}: {last}")

# --------------------------------------------------------------- aggregation
def aggregate(bars, keyfn, labfn):
    out = {}
    for b in bars:
        k = keyfn(b["dt"])
        if k not in out:
            out[k] = {"dt": b["dt"], "o": b["o"], "h": b["h"],
                      "l": b["l"], "c": b["c"], "v": b["v"], "label": labfn(k)}
        else:
            u = out[k]
            u["h"] = max(u["h"], b["h"]); u["l"] = min(u["l"], b["l"])
            u["c"] = b["c"]; u["v"] += b["v"]
    return [out[k] for k in sorted(out)]

def to_daily(bars):
    d = aggregate(bars, lambda dt: dt.date(), lambda k: k.strftime("%Y-%m-%d"))
    return d

def to_weekly(daily):
    def key(dt):
        iso = dt.date().isocalendar()
        return (iso[0], iso[1])
    def lab(k):
        from datetime import date as _date
        return _date.fromisocalendar(k[0], k[1], 1).strftime("%Y-%m-%d")
    return aggregate(daily, key, lab)

def to_monthly(daily):
    return aggregate(daily, lambda dt: (dt.year, dt.month),
                     lambda k: f"{k[0]}-{k[1]:02d}")

def to_yearly(daily):
    return aggregate(daily, lambda dt: (dt.year,), lambda k: str(k[0]))

def sma_series(bars, n):
    out = [None] * len(bars); run = 0.0
    for i, b in enumerate(bars):
        run += b["c"]
        if i >= n: run -= bars[i - n]["c"]
        if i >= n - 1: out[i] = run / n
    return out

def atr_series(bars, n=ATR_LEN):
    """Simple-average true range over the n bars ending at each bar."""
    trs = []
    for i, b in enumerate(bars):
        if i == 0:
            trs.append(b["h"] - b["l"])
        else:
            pc = bars[i - 1]["c"]
            trs.append(max(b["h"] - b["l"], abs(b["h"] - pc), abs(b["l"] - pc)))
    out = [None] * len(bars)
    for i in range(len(bars)):
        if i >= 2:                       # need at least a few bars to be sane
            w = trs[max(0, i - n + 1):i + 1]
            out[i] = mean(w)
    return out

# -------------------------------------------------------------------- regime
def daily_regime_lut(daily):
    ma = sma_series(daily, 200); lut = {}
    for i, b in enumerate(daily):
        if ma[i] is None or i < 220:
            lut[b["dt"].date()] = "UNKNOWN"; continue
        if b["c"] > ma[i] and ma[i] > ma[i - 20]: r = "UPTREND"
        elif b["c"] < ma[i] and ma[i] < ma[i - 20]: r = "DOWNTREND"
        else: r = "SIDEWAYS"
        lut[b["dt"].date()] = r
    return lut

def regime_before(lut, dates_sorted, when):
    prev = None
    for d in dates_sorted:
        if d < when: prev = d
        else: break
    return lut.get(prev, "UNKNOWN") if prev else "UNKNOWN"

def make_regimes(daily_ctx, monthly):
    lut = daily_regime_lut(daily_ctx); dates_sorted = sorted(lut.keys())
    regime_daily = lambda j, bar: regime_before(lut, dates_sorted, bar["dt"].date())
    ma_m = sma_series(monthly, 10)
    def regime_monthly(j, bar):
        if ma_m[j] is None or j < 3: return "UNKNOWN"
        if bar["c"] > ma_m[j] and ma_m[j] > ma_m[j - 3]: return "UPTREND"
        if bar["c"] < ma_m[j] and ma_m[j] < ma_m[j - 3]: return "DOWNTREND"
        return "SIDEWAYS"
    def regime_yearly(j, bar):
        yr = bar["dt"].year
        cand = [i for i, mb in enumerate(monthly)
                if mb["dt"].year == yr and mb["dt"].month == 12]
        if not cand:
            cand = [i for i, mb in enumerate(monthly) if mb["dt"].year == yr]
        return regime_monthly(cand[-1], monthly[cand[-1]]) if cand else "UNKNOWN"
    return regime_daily, regime_monthly, regime_yearly

# ------------------------------------------------- pullback volume baseline
def pullback_baseline(V, j, trail_mean):
    """
    Mean volume of the final quiet pullback/consolidation cluster
    immediately before breakout bar j. Precise definition:
      * a bar is QUIET if its volume is below trail_mean (the trailing
        20-bar mean volume, the same baseline as the trailing ratio);
      * look at bars j-1, j-2, ... : bar j-1 may be skipped once if it is
        not quiet (it is often itself the launch bar of the move); after
        that, collect the consecutive quiet bars, at most
        PULLBACK_QUIET_MAX_BARS of them, stopping at the first non-quiet bar;
      * if no quiet bar is collected, fall back to the mean volume of the
        (up to) 3 bars immediately before j.
    Returns the baseline mean volume (the caller forms the ratio).
    """
    if j <= 0 or trail_mean != trail_mean or trail_mean <= 0:
        return float("nan")
    quiet = []
    m = j - 1
    if m >= 0 and V[m] >= trail_mean:
        m -= 1                                   # skip one launch bar
    while m >= 0 and len(quiet) < PULLBACK_QUIET_MAX_BARS and V[m] < trail_mean:
        quiet.append(V[m]); m -= 1
    if quiet:
        return mean(quiet)
    back = V[max(0, j - 3):j]
    return mean(back) if back else float("nan")

# ------------------------------------------------------------------ detector
def detect(bars, layer, cfg, regime_fn, own_ma, level, vol_ratio_pullback):
    """Find breakout events at one layer and one level ("MAJOR" or "SMALL").

    MAJOR point = formed swing high that is HISTORIC or VOLUME-FORMED.
    SMALL point = formed swing high that is neither.
    Everything else (grading, walk classification, recorded fields) is
    identical for the two levels.
    """
    n = len(bars)
    H = [b["h"] for b in bars]; C = [b["c"] for b in bars]; V = [b["v"] for b in bars]
    ATR = atr_series(bars)
    k = cfg["k"]; points = []

    def formed_count(i):
        lo = max(0, i - cfg["formed_span"]); hi = min(n - 1, i + cfg["formed_span"])
        return sum(1 for m in range(lo, hi + 1) if H[m] >= H[i] * (1 - cfg["formed_band"]))

    def vol_formed(i):
        w = cfg["vol_form_win"]; mw = cfg["vol_med_win"]
        if i - w - mw < 0: return False
        base = median(V[i - w - mw:i - w])
        return base > 0 and mean(V[i - w:i + w + 1]) >= cfg["vol_thresh"] * base

    for i in range(n):
        lo = max(0, i - k); hi = min(n - 1, i + k)
        if H[i] != max(H[lo:hi + 1]):
            continue
        if formed_count(i) < cfg["formed_min"]:
            continue                                    # spike tip / thin top
        lb = cfg["hist_lookback"]; start = max(0, i - lb)
        historic = i > start and H[i] >= max(H[start:i])
        vf = vol_formed(i)
        qualifies = (historic or vf) if level == "MAJOR" else (not historic and not vf)
        if qualifies:
            points.append({"idx": i, "level": H[i], "historic": bool(historic),
                           "vol_formed": bool(vf), "confirm_at": i + k})
    if level == "MAJOR" and cfg["seed_first"] and n and \
            not any(p["idx"] == 0 for p in points):
        points.append({"idx": 0, "level": H[0], "historic": True,
                       "vol_formed": False, "confirm_at": 0, "seeded": True})
    points.sort(key=lambda p: p["idx"])
    dedup = []
    for p in points:
        if dedup and abs(p["level"] - dedup[-1]["level"]) / dedup[-1]["level"] < 0.001 \
           and p["idx"] - dedup[-1]["idx"] <= 2 * k:
            continue
        dedup.append(p)
    points = dedup

    events = []; active = []; ptr = 0
    pts = sorted(points, key=lambda p: p["confirm_at"])
    for j in range(n):
        while ptr < len(pts) and pts[ptr]["confirm_at"] <= j:
            active.append(pts[ptr]); ptr += 1
        if j == 0: continue
        broken = sorted([p for p in active if C[j] > p["level"]],
                        key=lambda p: p["level"])
        if not broken: continue
        main = broken[-1]
        broken_ids = {id(p) for p in broken}
        active = [p for p in active if id(p) not in broken_ids]
        b = bars[j]; prev_close = C[j - 1]
        body = b["c"] - b["o"]
        gap = max(0.0, b["o"] - prev_close)
        eff_len = (b["c"] - prev_close) if b["o"] >= prev_close else body
        eff_pct = eff_len / prev_close * 100 if prev_close else 0.0
        prior_bodies = [abs(bars[m]["c"] - bars[m]["o"]) / bars[m]["o"] * 100
                        for m in range(max(0, j - 60), j)]
        med_body = median(prior_bodies) if prior_bodies else float("nan")
        if cfg["vol_ok"]:
            base_vol = V[max(0, j - 20):j]
            trail_mean = mean(base_vol) if base_vol else float("nan")
            vol_ratio = V[j] / trail_mean if trail_mean == trail_mean and trail_mean > 0 \
                else float("nan")
            pb_base = pullback_baseline(V, j, trail_mean)
            vol_pb = V[j] / pb_base if pb_base == pb_base and pb_base > 0 \
                else float("nan")
        else:
            vol_ratio = float("nan"); vol_pb = float("nan")
        # direction is tested on effective length (close vs prior close):
        # a bar that gaps up and fades from its open but closes above the
        # prior close is the up-candle the method means.
        yang = eff_len > 0
        length_ok = med_body == med_body and eff_pct >= med_body
        # volume tiers on the two baselines
        if cfg["vol_ok"]:
            tier2 = (vol_ratio >= VOL_RATIO_STANDARD) or \
                    (vol_pb >= vol_ratio_pullback and
                     vol_ratio >= VOL_RATIO_PARTIAL_FLOOR)
            tier1 = (not tier2) and (vol_ratio >= VOL_RATIO_PARTIAL_FLOOR or
                                     vol_pb >= VOL_RATIO_PARTIAL_FLOOR)
        else:
            tier2 = False; tier1 = False
        if cfg["vol_ok"] and yang and length_ok and tier2:
            grade = "STANDARD"
        elif yang and ((length_ok and tier1) or (tier2 and not length_ok)
                       or (not cfg["vol_ok"] and length_ok)):
            grade = "PARTIAL"
        else:
            grade = "WEAK"
        above = [p["level"] for p in points
                 if p["confirm_at"] <= j and p["level"] > main["level"]
                 and id(p) not in broken_ids]
        above += [p["level"] for p in active if p["level"] > main["level"]]
        next_res = min(above) if above else None

        # ---- the walk (what price does after the break)
        W = cfg["window"]; end = min(n - 1, j + W)
        bottom = b["l"]; bclose = b["c"]; span = bclose - bottom
        level_price = main["level"]
        fail_at = None; last = end
        for m in range(j + 1, end + 1):
            if bars[m]["c"] < bottom:
                fail_at = m; last = m; break
        # first retracement segment: bars after the breakout bar up to and
        # including the first close back above the breakout close
        # (recovery), or the failure bar, or the window end.
        seg_last = last
        recovered = False
        for m in range(j + 1, last + 1):
            if bars[m]["c"] > bclose:
                seg_last = m; recovered = True; break
        seg = list(range(j + 1, seg_last + 1))
        if seg:
            max_high = max(bars[x]["h"] for x in range(j + 1, last + 1))
            deepest_low = min(bars[x]["l"] for x in seg)
            deepest_close = min(bars[x]["c"] for x in seg)
        else:
            max_high = b["h"]; deepest_low = b["l"]; deepest_close = bclose
        depth = (bclose - deepest_low) / span if span > 0 else 0.0
        depth_closes = max(0.0, (bclose - deepest_close) / span) if span > 0 else 0.0
        # pullback volume = MEDIAN volume of the segment bars (a single
        # maximum bar would be structurally biased to "enlarged")
        if seg:
            pull_med = median([V[x] for x in seg])
            vol_enlarged = pull_med > V[j]
        else:
            vol_enlarged = False
        max_adv = (max_high - level_price) / level_price * 100 if max_high > 0 else 0.0
        reached_res = bool(next_res and max_high >= next_res) if next_res else None
        # gating of the depth-based FALSE branch + substance override
        given_back = bars[last]["c"] < level_price if last > j else False
        if fail_at is not None:
            walk = "FALSE"
        elif depth <= 1 / 3:
            walk = "RUNS STRAIGHT UP"
        elif depth <= 0.5:
            cont = recovered or bars[last]["c"] > level_price
            walk = "SHALLOW PULLBACK" if (not vol_enlarged and cont) else "MIXED"
        else:
            walk = "FALSE" if (vol_enlarged and given_back) else "MIXED"
        if walk == "FALSE" and fail_at is None and \
           (reached_res or max_adv >= SUBSTANCE_ADVANCE_PCT):
            walk = "MIXED"
        # recorded fields: throwback to the broken level, ATR race
        throwback = False; bars_to_throwback = None
        for m in range(j + 1, last + 1):
            if bars[m]["l"] <= level_price:
                throwback = True; bars_to_throwback = m - j; break
        atr_race = "—"
        if ATR[j] is not None and ATR[j] > 0:
            up_lvl = bclose + ATR[j]; dn_lvl = bclose - ATR[j]
            up_at = dn_at = None
            for m in range(j + 1, last + 1):
                if up_at is None and bars[m]["h"] >= up_lvl: up_at = m
                if dn_at is None and bars[m]["l"] <= dn_lvl: dn_at = m
                if up_at is not None and dn_at is not None: break
            if up_at is not None and dn_at is None: atr_race = "Y"
            elif dn_at is not None and up_at is None: atr_race = "N"
            elif up_at is not None and dn_at is not None:
                atr_race = "Y" if up_at < dn_at else ("N" if dn_at < up_at else "—")
        own = None
        if own_ma is not None and own_ma[j] is not None:
            own = "ABOVE" if b["c"] > own_ma[j] else "BELOW"
        # honesty flags: could this point's formation volume even be
        # evaluated (enough bars before it)? For SMALL points an
        # unevaluable point is a window-edge artifact — the point might be
        # major on longer history; the flag says so instead of hiding it.
        evaluable = main["idx"] - cfg["vol_form_win"] - cfg["vol_med_win"] >= 0
        if level == "SMALL":
            point_kind = "SMALL"; seeded = False
        else:
            point_kind = ("HISTORIC" if main["historic"] else "") + \
                         ("+VOLUME" if main["vol_formed"] else "")
            seeded = bool(main.get("seeded"))
        events.append({
            "layer": layer, "level": level, "date": b["label"],
            "level_broken": round(main["level"], 2),
            "points_broken": [round(p["level"], 2) for p in broken],
            "point_kind": point_kind,
            "seeded_point": seeded,
            "formation_vol_evaluable": bool(evaluable),
            "window_edge_artifact": bool(level == "SMALL" and not evaluable),
            "open": round(b["o"], 2), "high": round(b["h"], 2),
            "low": round(b["l"], 2), "close": round(b["c"], 2),
            "body_pct": round(body / b["o"] * 100, 2) if b["o"] else 0.0,
            "gap_pct": round(gap / prev_close * 100, 2) if prev_close else 0.0,
            "eff_len_pct": round(eff_pct, 2),
            "median_body_pct": round(med_body, 2) if med_body == med_body else None,
            "vol_ratio": round(vol_ratio, 2) if vol_ratio == vol_ratio else None,
            "vol_ratio_pullback": round(vol_pb, 2) if vol_pb == vol_pb else None,
            "grade": grade, "walk": walk, "depth_frac": round(depth, 3),
            "depth_frac_closes": round(depth_closes, 3),
            "max_advance_pct": round(max_adv, 2),
            "bars_to_failure": (fail_at - j) if fail_at is not None else None,
            "window_bars_used": last - j,
            "next_resistance": round(next_res, 2) if next_res else None,
            "reached_next_resistance": reached_res,
            "throwback_to_level": throwback,
            "bars_to_throwback": bars_to_throwback,
            "atr_race": atr_race,
            "regime": regime_fn(j, b), "own_long_avg": own,
            "success": walk in ("RUNS STRAIGHT UP", "SHALLOW PULLBACK"),
        })
    return events, points

# --------------------------------------------------------------------- stats
def layer_stats(evs):
    n = len(evs)
    def rate(successes, total): return round(100 * successes / total, 1) if total else None
    by_grade = {}
    for g in ("STANDARD", "PARTIAL", "WEAK"):
        sub = [e for e in evs if e["grade"] == g]
        by_grade[g] = {"n": len(sub),
                       "success_rate": rate(sum(1 for e in sub if e["success"]), len(sub))}
    by_regime = {}
    for r in ("UPTREND", "DOWNTREND", "SIDEWAYS", "UNKNOWN"):
        sub = [e for e in evs if e["regime"] == r]
        if sub:
            by_regime[r] = {"n": len(sub),
                            "success_rate": rate(sum(1 for e in sub if e["success"]), len(sub))}
    cross = {}
    for r in ("UPTREND", "DOWNTREND", "SIDEWAYS", "UNKNOWN"):
        row = {}
        for w in ("RUNS STRAIGHT UP", "SHALLOW PULLBACK", "FALSE", "MIXED"):
            c = sum(1 for e in evs if e["regime"] == r and e["walk"] == w)
            if c: row[w] = c
        if row: cross[r] = row
    walks = Counter(e["walk"] for e in evs)
    fails = [e["bars_to_failure"] for e in evs if e.get("bars_to_failure")]
    succ = sum(1 for e in evs if e["success"])
    return {"n": n,
            "success_rate": rate(succ, n),
            "false_rate": rate(sum(1 for e in evs if e["walk"] == "FALSE"), n),
            "grades": dict(Counter(e["grade"] for e in evs)),
            "walks": dict(walks),
            "by_grade": by_grade, "by_regime": by_regime,
            "walk_x_regime": cross,
            "most_common_walk_overall": walks.most_common(1)[0][0] if walks else None,
            "median_bars_to_failure": median(fails) if fails else None,
            "throwback_rate": rate(sum(1 for e in evs if e["throwback_to_level"]), n),
            "atr_race": dict(Counter(e["atr_race"] for e in evs)),
            "sample_block": sample_block(n, succ)}

# -------------------------------------------------------------------- report
def write_report(path, meta, results, stats):
    L = []
    L.append(f"# Breakout Character Report — {meta['instrument']}")
    L.append("")
    L.append(f"Base timeframe: {meta['timeframe']} · bars: {meta['bars']} "
             f"({meta['range'][0]} → {meta['range'][1]}) · "
             f"pullback-relative volume threshold: {meta['vol_ratio_pullback']}")
    L.append("")
    L.append("Walks: RSU = runs straight up · SP = shallow pullback · "
             "F = FALSE · M = MIXED. Success = RSU + SP.")
    L.append("")
    L.append("| Cell | n | Success | RSU | SP | F | M | Fail median |")
    L.append("|---|---|---|---|---|---|---|---|")
    for key, evs in results.items():
        w = Counter(e["walk"] for e in evs)
        s = stats[key]
        L.append(f"| {key} | {s['n']} | {s['success_rate']}% | "
                 f"{w.get('RUNS STRAIGHT UP', 0)} | {w.get('SHALLOW PULLBACK', 0)} | "
                 f"{w.get('FALSE', 0)} | {w.get('MIXED', 0)} | "
                 f"{s['median_bars_to_failure']} |")
    L.append("")
    L.append("## Sample-size block — every cell")
    L.append("")
    L.append("Needed = events required at 95% confidence from the observed "
             "rate (worst case at a 50% rate in brackets). Grade: within "
             "+/-5 = TRUSTWORTHY · within +/-10 = BARELY USABLE · beyond "
             "+/-10 = TREND ONLY, never a rate.")
    L.append("")
    L.append("| Cell | Needed +/-5 | Needed +/-10 | In hand | Achieved | Grade |")
    L.append("|---|---|---|---|---|---|")
    for key in results:
        sb = stats[key]["sample_block"]
        L.append(f"| {key} | {sb['needed_pm5']} [{sb['needed_pm5_worst']}] | "
                 f"{sb['needed_pm10']} [{sb['needed_pm10_worst']}] | {sb['n']} | "
                 f"+/-{sb['achieved_pm']} | {sb['grade']} |")
    L.append("")
    L.append("## How to read this")
    L.append("")
    L.append("- A success rate is only as good as its achieved margin. "
             "TREND ONLY cells describe a direction, not a probability "
             "you can size a trade on.")
    L.append("- Events are not statistically independent (breakouts cluster "
             "in strong runs, and the same physical top can appear at "
             "several layers), so treat pooled figures as orientation.")
    L.append("- Candle grade is descriptive. In the reference study it did "
             "not separate success from failure; the separation appeared "
             "in the walk — above all in the first retracement's depth and "
             "in whether price ever closed below the breakout candle's low.")
    L.append("- This tool measures history. It does not predict, and it is "
             "not financial advice.")
    Path(path).write_text("\n".join(L) + "\n")

# ---------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Breakout Character Analyzer — per-instrument breakout "
                    "statistics with sample sizes and margins of error.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", help="CSV file with columns date,o,h,l,c,v")
    src.add_argument("--symbol", help="ticker to fetch from Yahoo Finance")
    ap.add_argument("--timeframe", choices=["daily", "hourly"], default="daily",
                    help="timeframe of the input/fetch (default daily)")
    ap.add_argument("--fetch-range", default=None,
                    help="Yahoo range for --symbol (daily default 10y; "
                         "hourly is fixed at 730d, Yahoo's maximum)")
    ap.add_argument("--layers", default=None,
                    help="comma list, e.g. DAILY,WEEKLY (default: all "
                         "layers derivable from the timeframe)")
    ap.add_argument("--levels", default="major,small",
                    help="comma list: major,small (default both)")
    ap.add_argument("--context", default=None,
                    help="optional daily CSV used only for regime context")
    ap.add_argument("--vol-ratio-pullback", type=float, default=1.2,
                    help="pullback-relative volume threshold for the "
                         "STANDARD grade (default 1.2; touches grades only)")
    ap.add_argument("--out", default="./breakout-results",
                    help="output directory (default ./breakout-results)")
    ap.add_argument("--report", default=None,
                    help="also write a Markdown report to this path")
    args = ap.parse_args(argv)

    if args.input:
        bars = read_csv_bars(args.input, args.timeframe)
        instrument = Path(args.input).stem
    else:
        if args.timeframe == "hourly":
            raw = fetch_yahoo(args.symbol, "730d", "1h")
            bars = [b for b in raw if (b["dt"].hour, b["dt"].minute) in
                    {(9, 30), (10, 30), (11, 30), (12, 30), (13, 30),
                     (14, 30), (15, 30)}]
            for b in bars: b["label"] = b["dt"].strftime("%Y-%m-%d %H:%M")
        else:
            bars = fetch_yahoo(args.symbol, args.fetch_range or "10y", "1d")
            for b in bars: b["label"] = b["dt"].strftime("%Y-%m-%d")
        instrument = args.symbol
    if not bars:
        print("no bars loaded", file=sys.stderr); return 1

    daily = bars if args.timeframe == "daily" else to_daily(bars)
    if args.context:
        daily_ctx = read_csv_bars(args.context, "daily")
    else:
        daily_ctx = daily
    weekly = to_weekly(daily); monthly = to_monthly(daily); yearly = to_yearly(daily)
    regime_daily, regime_monthly, regime_yearly = make_regimes(daily_ctx, monthly)

    layer_bars = {"HOURLY": bars if args.timeframe == "hourly" else None,
                  "DAILY": daily, "WEEKLY": weekly,
                  "MONTHLY": monthly, "YEARLY": yearly}
    layer_regime = {"HOURLY": regime_daily, "DAILY": regime_daily,
                    "WEEKLY": regime_daily, "MONTHLY": regime_monthly,
                    "YEARLY": regime_yearly}
    layer_own = {"HOURLY": sma_series(bars, 200) if args.timeframe == "hourly" else None,
                 "DAILY": sma_series(daily, 200), "WEEKLY": sma_series(weekly, 40),
                 "MONTHLY": sma_series(monthly, 10), "YEARLY": None}

    want_layers = ([s.strip().upper() for s in args.layers.split(",")]
                   if args.layers else list(DERIVABLE[args.timeframe]))
    want_levels = [s.strip().lower() for s in args.levels.split(",")]
    bad = [x for x in want_layers if x not in DERIVABLE[args.timeframe]]
    if bad:
        print(f"layers {bad} cannot be derived from {args.timeframe} input",
              file=sys.stderr); return 1

    results = {}; stats = {}
    for layer in LAYER_ORDER:
        if layer not in want_layers: continue
        lb = layer_bars[layer]
        if lb is None: continue
        for lvl in ("MAJOR", "SMALL"):
            if lvl.lower() not in want_levels: continue
            cfg = dict(PARAMS[layer])
            if lvl == "SMALL":
                cfg["seed_first"] = False
            evs, _pts = detect(lb, layer, cfg, layer_regime[layer],
                               layer_own[layer], lvl, args.vol_ratio_pullback)
            key = f"{layer}-{lvl}"
            results[key] = evs
            stats[key] = layer_stats(evs)
    all_ev = [e for evs in results.values() for e in evs]
    stats["ALL_CELLS"] = layer_stats(all_ev)

    meta = {"instrument": instrument, "timeframe": args.timeframe,
            "bars": len(bars), "range": [bars[0]["label"], bars[-1]["label"]],
            "vol_ratio_pullback": args.vol_ratio_pullback,
            "layers": sorted({k.split("-")[0] for k in results}),
            "levels": sorted({k.split("-")[1] for k in results})}
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    with open(out / "events.json", "w") as f:
        json.dump({"meta": meta, "events": results, "stats": stats}, f, indent=1)
    with open(out / "stats.json", "w") as f:
        json.dump({"meta": meta, "stats": stats}, f, indent=1)
    fields = list(all_ev[0].keys()) if all_ev else []
    if fields:
        with open(out / "events.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
            for e in all_ev: w.writerow(e)
    if args.report:
        write_report(args.report, meta, results, stats)

    print(f"{instrument} · {args.timeframe} · {len(bars)} bars · "
          f"{bars[0]['label']} → {bars[-1]['label']}")
    print(f"{'cell':<18} {'n':>5} {'success':>8} {'achieved':>9}  grade")
    for key in results:
        s = stats[key]; sb = s["sample_block"]
        print(f"{key:<18} {s['n']:>5} {str(s['success_rate']) + '%':>8} "
              f"{('+/-' + str(sb['achieved_pm'])) if sb['achieved_pm'] is not None else '—':>9}  "
              f"{sb['grade']}")
    print(f"outputs in {out}/  (events.json, events.csv, stats.json)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
