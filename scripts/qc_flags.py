"""
qc_flags.py
dataset_v2_3.csv ke liye QC flags banata hai. Rows DELETE nahi hoti, sirf flag lagta hai.
Output: data/processed/qc_flags_v2_3.csv  (SITE_ID, DATE, flags). Badi dataset file dobara nahi banti.

Flags:
  QC_RANGE               level < 0 ya > 300 m                      (purana OUTLIER)
  QC_JUMP                |level_trend_lag1_lag2_m| > 50 m          (do readings ke beech bahut bada kood)
  QC_LEVEL_GT_WELLDEPTH  WLS_WTR_LEVEL > WELL_DEPTH + TOL_M        (paani well ki gehrai se neeche, sambhav nahi)
  QC_ANY                 inme se koi bhi

Chalao (C:\\Ground water se):
    python scripts\\qc_flags.py
"""
from pathlib import Path

import pandas as pd

P = Path("data/processed")
SRC = P / "dataset_v2_3.csv"
OUT = P / "qc_flags_v2_3.csv"
JUMP_M = 50.0
TOL_M = 0.0          # 1.0 karke dekh sakte ho (well depth ki rounding ke liye)
MARKER = "## QC flags (v2_3)"

d = pd.read_csv(SRC, dtype={"SITE_ID": str}, low_memory=False)
need = ["SITE_ID", "DATE", "WLS_WTR_LEVEL", "WELL_DEPTH", "level_trend_lag1_lag2_m", "YEAR"]
miss = [c for c in need if c not in d.columns]
if miss:
    raise SystemExit(f"Ye columns dataset mein nahi mile: {miss}")

# Split column na ho to saal se bana lo
if "SPLIT" not in d.columns:
    d["SPLIT"] = "unused"
    ok = d["YEAR"].between(2005, 2023)
    d.loc[ok & (d["YEAR"] <= 2020), "SPLIT"] = "train"
    d.loc[ok & (d["YEAR"] == 2021), "SPLIT"] = "val"
    d.loc[ok & (d["YEAR"] > 2021), "SPLIT"] = "test"

q = pd.DataFrame({"SITE_ID": d["SITE_ID"], "DATE": d["DATE"].astype(str)})
q["QC_RANGE"] = (d["WLS_WTR_LEVEL"] < 0) | (d["WLS_WTR_LEVEL"] > 300)
q["QC_JUMP"] = d["level_trend_lag1_lag2_m"].abs() > JUMP_M
q["QC_LEVEL_GT_WELLDEPTH"] = d["WELL_DEPTH"].notna() & (d["WLS_WTR_LEVEL"] > d["WELL_DEPTH"] + TOL_M)
q["QC_ANY"] = q[["QC_RANGE", "QC_JUMP", "QC_LEVEL_GT_WELLDEPTH"]].any(axis=1)
q.to_csv(OUT, index=False)

# Summary: flag x split
flags = ["QC_RANGE", "QC_JUMP", "QC_LEVEL_GT_WELLDEPTH", "QC_ANY"]
tab = pd.DataFrame({f: q[f].groupby(d["SPLIT"]).sum().astype(int) for f in flags})
tab["rows"] = d.groupby("SPLIT").size()
print("Flagged rows (split ke hisaab se):")
print(tab.to_string())
print(f"\nWELL_DEPTH ke saath TOL_M=1.0 par QC_LEVEL_GT_WELLDEPTH: "
      f"{int((d['WELL_DEPTH'].notna() & (d['WLS_WTR_LEVEL'] > d['WELL_DEPTH'] + 1.0)).sum())} rows")
print(f"Flagged stations (QC_ANY): {d.loc[q['QC_ANY'], 'SITE_ID'].nunique()}")
print(f"\nSaved: {OUT}")

# LIMITATIONS.md mein ek hi baar likho
lim = Path("data/processed/LIMITATIONS.md")
if lim.exists() and MARKER not in lim.read_text(encoding="utf-8"):
    tot = int(q["QC_ANY"].sum())
    with open(lim, "a", encoding="utf-8") as f:
        f.write(f"\n{MARKER}\n")
        f.write(f"- Suspicious rows are flagged, not deleted: level outside 0-300 m ({int(q['QC_RANGE'].sum())}), "
                f"|jump between last two readings| > {JUMP_M:.0f} m ({int(q['QC_JUMP'].sum())}), "
                f"level deeper than the recorded well depth ({int(q['QC_LEVEL_GT_WELLDEPTH'].sum())}). Total flagged: {tot}.\n")
        f.write("- Models are evaluated both with and without flagged rows; the rule was fixed before looking at test results.\n")
    print("LIMITATIONS.md mein QC section jod diya")
