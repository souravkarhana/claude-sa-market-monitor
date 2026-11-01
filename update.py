"""Daily EOD update: NSE bhavcopy -> MR20 / U4 / D4 / W20 -> data.json.

Run:  python update.py
Needs: pandas, requests.

Files it keeps in this folder:
  data.json        the site's data (oldest first), appended every run
  history.csv.gz   last ~150 trading days of per-stock close/volume (EMA warm-up)

Definitions (calibrate once against your Chartink numbers, see README):
  universe  EQ series stocks with turnover >= 10 crore that day
  MR20      % of universe with adjusted close above its 20-day EMA
  U4 / D4   close up / down 4%+ vs previous close AND volume above previous day
  W20       adjusted close up 20%+ vs 5 trading days ago
Prices are adjusted for splits/bonus using NSE's own previous-close column:
if today's PrevClose differs from yesterday's Close, older prices are rescaled.
"""
import datetime as dt
import io
import json
import os
import sys
import time
import zipfile

import pandas as pd
import requests

from sa_logic import enrich

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data.json")
HIST = os.path.join(HERE, "history.csv.gz")

TURNOVER_MIN = 10e7  # Rs 10 crore
U4_PCT = 0.04
WARMUP_DAYS = 150  # calendar days of history kept for the EMA

URLS = [
    # UDiFF format (NSE, from July 2024)
    "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip",
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/",
}
COLS = {  # UDiFF name -> our name (old-format names as fallback)
    "TckrSymb": "symbol", "SYMBOL": "symbol",
    "SctySrs": "series", "SERIES": "series",
    "ClsPric": "close", "CLOSE": "close",
    "PrvsClsgPric": "prev_close", "PREVCLOSE": "prev_close",
    "TtlTradgVol": "volume", "TOTTRDQTY": "volume",
    "TtlTrfVal": "turnover", "TOTTRDVAL": "turnover",
}


def fetch_day(day: dt.date, session: requests.Session):
    """Return a DataFrame for one trading day, or None (holiday / not published)."""
    ymd = day.strftime("%Y%m%d")
    for tpl in URLS:
        url = tpl.format(ymd=ymd)
        for attempt in range(3):
            try:
                r = session.get(url, headers=HEADERS, timeout=30)
            except requests.RequestException:
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code == 404:
                break
            if r.status_code != 200 or not r.content[:2] == b"PK":
                time.sleep(2 * (attempt + 1))
                continue
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                df = pd.read_csv(z.open(z.namelist()[0]))
            df = df.rename(columns=COLS)
            need = {"symbol", "series", "close", "prev_close", "volume", "turnover"}
            if not need.issubset(df.columns):
                print(f"{day}: unexpected columns {list(df.columns)[:12]}", file=sys.stderr)
                return None
            df = df[df["series"] == "EQ"][["symbol", "close", "prev_close", "volume", "turnover"]].copy()
            df.insert(0, "date", day.isoformat())
            return df
    return None


def load_history():
    if os.path.exists(HIST):
        return pd.read_csv(HIST)
    return pd.DataFrame(columns=["date", "symbol", "close", "prev_close", "volume", "turnover"])


def compute_day(hist: pd.DataFrame, day: str):
    """Compute MR20/U4/D4/W20/universe for `day` using history up to and including it."""
    h = hist[hist["date"] <= day]
    close = h.pivot(index="date", columns="symbol", values="close").sort_index()
    prev = h.pivot(index="date", columns="symbol", values="prev_close").sort_index()
    vol = h.pivot(index="date", columns="symbol", values="volume").sort_index()
    turn = h.pivot(index="date", columns="symbol", values="turnover").sort_index()

    # split/bonus adjustment: ratio of NSE's prev close to our stored previous close
    ratio = (prev / close.shift(1)).fillna(1.0)
    ratio = ratio.where((ratio - 1).abs() > 0.003, 1.0)
    factor = ratio.iloc[::-1].cumprod().iloc[::-1].shift(-1).fillna(1.0)
    adj = close * factor

    ema = adj.ewm(span=20, adjust=False, min_periods=20).mean()
    universe = turn.loc[day] >= TURNOVER_MIN
    last_adj, last_ema = adj.loc[day], ema.loc[day]
    valid = universe & last_ema.notna() & last_adj.notna()
    mr20 = round(100 * (last_adj[valid] > last_ema[valid]).mean(), 1)

    ret = close.loc[day] / prev.loc[day] - 1
    vol_up = vol.loc[day] > vol.shift(1).loc[day]
    u4 = int((universe & (ret >= U4_PCT) & vol_up).sum())
    d4 = int((universe & (ret <= -U4_PCT) & vol_up).sum())

    if len(adj) > 5:
        w = adj.loc[day] / adj.shift(5).loc[day] - 1
        w20 = int((universe & (w >= 0.20)).sum())
    else:
        w20 = 0
    return {"date": day, "MR20": float(mr20), "U4": u4, "D4": d4, "W20": w20,
            "universe": int(universe.sum())}


def main():
    with open(DATA) as f:
        payload = json.load(f)
    rows = payload["rows"]
    last = dt.date.fromisoformat(rows[-1]["date"])
    today = dt.date.today()

    hist = load_history()
    have = set(hist["date"].unique())
    start = today - dt.timedelta(days=WARMUP_DAYS)

    session = requests.Session()
    session.get("https://www.nseindia.com/", headers=HEADERS, timeout=30)  # cookies
    new_frames, fetched = [], []
    d = start
    while d <= today:
        if d.weekday() < 5 and d.isoformat() not in have:
            df = fetch_day(d, session)
            if df is not None:
                new_frames.append(df)
                fetched.append(d.isoformat())
            time.sleep(1)
        d += dt.timedelta(days=1)
    if new_frames:
        hist = pd.concat([hist] + new_frames, ignore_index=True)
    cutoff = (today - dt.timedelta(days=WARMUP_DAYS + 20)).isoformat()
    hist = hist[hist["date"] >= cutoff].sort_values(["date", "symbol"])
    hist.to_csv(HIST, index=False, compression="gzip")

    todo = [x for x in sorted(hist["date"].unique()) if x > rows[-1]["date"]]
    if not todo:
        print("No new trading days. Nothing to update.")
        return
    base = [{k: r[k] for k in ("date", "MR20", "U4", "D4", "W20", "universe")} for r in rows]
    for day in todo:
        base.append(compute_day(hist, day))
        print("added", base[-1])
    full = enrich(base)
    with open(DATA, "w") as f:
        json.dump({"updated": full[-1]["date"], "rows": full}, f, separators=(",", ":"))


if __name__ == "__main__":
    main()
