"""
download_climate2.py
NASA POWER daily data for the same 144 grid cells as rainfall_monthly.csv.
Parameters: T2M_MAX, T2M_MIN, GWETROOT, GWETTOP, EVLAND

Usage (from C:\\Ground water, venv active):
    python download_climate2.py test    # one cell, each parameter requested separately
    python download_climate2.py         # full download (resumable)

Does not touch any existing file. Output: data\\raw\\nasa_power_climate2_json\\<lat>_<lon>.json
"""
import sys
import time
import json
from pathlib import Path

import requests
import pandas as pd

ROOT = Path(r"C:\Ground water")
RAIN = ROOT / "data" / "processed" / "rainfall_monthly.csv"
OUT = ROOT / "data" / "raw" / "nasa_power_climate2_json"
OUT.mkdir(parents=True, exist_ok=True)

URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = ["T2M_MAX", "T2M_MIN", "GWETROOT", "GWETTOP", "EVLAND"]
START, END = "20040101", "20241231"
FILL = -900          # POWER fill value is -999; treat <= -900 as missing

cells = (pd.read_csv(RAIN)[["lat_grid", "lon_grid"]]
         .drop_duplicates().sort_values(["lat_grid", "lon_grid"])
         .values.tolist())


def fetch(lat, lon, params, tries=4):
    q = {"parameters": ",".join(params), "community": "AG",
         "latitude": lat, "longitude": lon,
         "start": START, "end": END, "format": "JSON"}
    for k in range(tries):
        try:
            r = requests.get(URL, params=q, timeout=180)
            if r.status_code == 200:
                return r.json()
            print(f"  HTTP {r.status_code}: {r.text[:200]}")
            if r.status_code in (400, 422):      # bad request: retrying will not help
                return None
        except requests.RequestException as e:
            print("  network error:", e)
        time.sleep(5 * (k + 1))
    return None


def test():
    lat, lon = cells[len(cells) // 2]
    print(f"cells: {len(cells)} (144 aana chahiye) | test cell: {lat}, {lon}\n")
    for p in PARAMS:
        j = fetch(lat, lon, [p])
        if j is None:
            print(f"{p:9s} -> FAIL (parameter ka naam ya request galat)")
            continue
        d = j["properties"]["parameter"].get(p)
        if not d:
            print(f"{p:9s} -> response mein data nahi")
            continue
        s = pd.Series(d, dtype=float)
        v = s[s > FILL]
        info = j.get("parameters", {}).get(p, {})
        print(f"{p:9s} days={len(s)} valid={len(v)} min={v.min():.2f} "
              f"max={v.max():.2f} mean={v.mean():.2f} zeros={(v == 0).sum()} "
              f"| {info.get('units', '?')} | {str(info.get('longname', '?'))[:60]}")
        if p == "EVLAND":
            share = (v == 0).mean() if len(v) else 1.0
            print(f"          EVLAND zero share = {share:.1%} ->",
                  "DROP EVLAND (almost all zero)" if share > 0.9 else "usable, plausibility check baaki")
    print("\nSample (T2M_MAX/T2M_MIN first 3 days):")
    j = fetch(lat, lon, ["T2M_MAX", "T2M_MIN"])
    if j:
        pm = j["properties"]["parameter"]
        for day in list(pm["T2M_MAX"])[:3]:
            print(day, pm["T2M_MAX"][day], pm["T2M_MIN"][day])


def full():
    t0 = time.time()
    for i, (lat, lon) in enumerate(cells, 1):
        f = OUT / f"{lat}_{lon}.json"
        if f.exists():
            continue
        j = fetch(lat, lon, PARAMS)
        if j is None:
            print(f"[{i}/{len(cells)}] FAIL {lat},{lon} (dobara chalao, ye cell dobara try hoga)")
            continue
        f.write_text(json.dumps(j["properties"]["parameter"]), encoding="utf-8")
        print(f"[{i}/{len(cells)}] saved {f.name} | {time.time() - t0:.0f}s")
        time.sleep(1.5)
    done = len(list(OUT.glob("*.json")))
    print(f"\nfiles: {done}/{len(cells)}")


if __name__ == "__main__":
    test() if len(sys.argv) > 1 and sys.argv[1] == "test" else full()
