"""
download_climate_extra.py
NASA POWER se temperature (T2M) aur humidity (RH2M), wahi 144 rainfall grid cells ke liye,
2004-2024 daily. Phir monthly average banata hai -> data/processed/climate_monthly.csv

PEHLE test karo (sirf 1 cell):
    python download_climate_extra.py test
Sahi chale to poora:
    python download_climate_extra.py

Agar 'requests' nahi hai:  pip install requests
Download dobara chalane par jo cells ho chuke hain wo skip ho jaate hain.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import requests
except ImportError:
    raise SystemExit("pip install requests  (pehle ye chalao)")

PROC = Path("data/processed")
RAW = Path("data/raw/nasa_power_climate_json")
URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = "T2M,RH2M"
START, END = "20040101", "20241231"
MIN_VALID_DAYS = 20          # mahine mein itne se kam valid din ho to value NaN


def get_cells():
    """Rainfall wale wahi grid cells (lat_grid, lon_grid)."""
    r = pd.read_csv(PROC / "rainfall_monthly.csv", usecols=["lat_grid", "lon_grid"]).drop_duplicates()
    return [(round(float(a), 3), round(float(b), 3)) for a, b in r.itertuples(index=False)]


def cell_file(lat, lon):
    return RAW / f"clim_lat_{lat}_lon_{lon}.json"


def fetch(lat, lon):
    f = cell_file(lat, lon)
    if f.exists() and f.stat().st_size > 1000:
        return "cached"
    params = dict(parameters=PARAMS, community="AG", latitude=lat, longitude=lon,
                  start=START, end=END, format="JSON")
    for attempt in range(1, 4):
        try:
            r = requests.get(URL, params=params, timeout=180)
            if r.status_code == 200:
                f.write_text(r.text, encoding="utf-8")
                return "ok"
            print(f"   HTTP {r.status_code} (attempt {attempt}): {r.text[:150]}")
        except requests.RequestException as e:
            print(f"   network error (attempt {attempt}): {e}")
        time.sleep(5 * attempt)
    return "failed"


def parse_month(f, lat, lon):
    """Ek cell ki JSON se monthly average (T2M, RH2M)."""
    j = json.loads(f.read_text(encoding="utf-8"))
    par = j["properties"]["parameter"]
    df = pd.DataFrame({k: pd.Series(v) for k, v in par.items() if k in ("T2M", "RH2M")})
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df = df.mask(df <= -900)     # NASA ka fill value -999 hota hai
    g = df.groupby([df.index.year, df.index.month])
    m = g.agg(t2m_mean_c=("T2M", "mean"), rh2m_mean_pct=("RH2M", "mean"),
              valid_days=("T2M", "count"))
    m.index.names = ["YEAR", "MONTH"]
    m = m.reset_index()
    bad = m["valid_days"] < MIN_VALID_DAYS
    m.loc[bad, ["t2m_mean_c", "rh2m_mean_pct"]] = np.nan
    m.insert(0, "lon_grid", lon)
    m.insert(0, "lat_grid", lat)
    m["date"] = pd.to_datetime(dict(year=m["YEAR"], month=m["MONTH"], day=1)).dt.strftime("%Y-%m-%d")
    return m


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    cells = get_cells()
    print(f"Grid cells: {len(cells)}")
    test = len(sys.argv) > 1 and sys.argv[1] == "test"
    todo = cells[:1] if test else cells

    status = {}
    for i, (lat, lon) in enumerate(todo, 1):
        s = fetch(lat, lon)
        status[(lat, lon)] = s
        print(f"[{i}/{len(todo)}] lat {lat} lon {lon}: {s}")
        if s == "ok":
            time.sleep(1.0)      # server par halka rakho

    done = [c for c, s in status.items() if s in ("ok", "cached")]
    frames = [parse_month(cell_file(*c), *c) for c in done]
    if not frames:
        raise SystemExit("Koi cell download nahi hua. Upar ke error dekho.")
    out = pd.concat(frames, ignore_index=True)

    if test:
        print("\nTEST OK. Pehle 6 rows:")
        print(out.head(6).to_string(index=False))
        print("\nAb poora chalao:  python download_climate_extra.py")
    else:
        out.to_csv(PROC / "climate_monthly.csv", index=False)
        print(f"\nSaved climate_monthly.csv: {len(out)} rows (144 x 252 = 36288 hone chahiye)")
        print("Failed cells:", [c for c, s in status.items() if s == "failed"])
        print("Missing t2m %:", round(out["t2m_mean_c"].isna().mean() * 100, 2))
