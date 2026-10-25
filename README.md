# AI-Based Groundwater Intelligence & Borewell Advisory System

Rajasthan ke liye groundwater level ka prediction aur borewell depth advisory.

## Problem
Rajasthan mein groundwater level gir raha hai aur log borewell contractor ke guesswork par khodte hain.
Failed borewell se Rs 1 se 5 lakh ka nuksaan hota hai. Sarkari tools sirf past aur current data dikhate hain.

## Kya banaya hai
1. **Prediction:** district / block ke liye agle round ka groundwater level (depth to water, metre mein; zyada = paani neeche).
2. **Advisory:** aas-paas ke wells ke historical data se borewell ki gehrai.
3. Model **WELL_DEPTH ke bina** chalta hai, kyunki naye borewell ke liye depth pehle se pata nahi hoti.

## Folder structure
```
scripts/     data pipeline (download, merge, features, QC) aur model_utils.py
notebooks/   model notebooks (baseline, ablation, XGBoost, validation, interval)
docs/        LIMITATIONS.md, data dictionaries, reports
backend/     FastAPI backend
frontend/    React + Leaflet dashboard
models/      final model files (git mein nahi, drive par)
data/        raw/ aur processed/ (git mein nahi, drive par)
```

## Data (git mein nahi hai)
Badi data files git mein nahi hain. Team drive par zip hai: **<link yahan daalo>**.
Har baar jis dataset version par kaam ho wo yahan likho: **dataset_v2_3.csv** (92,452 rows, 77 columns, 2005-2023 modeling window).

Sources:
- Water level: CGWB monitoring network, India Data Portal / India-WRIS mirror (Open Data Commons Attribution License)
- Rainfall, temperature, humidity, soil wetness: NASA POWER (0.5 degree grid, 144 cells)
- Elevation: SRTM30 (OpenTopoData)
- Stage of Extraction: CGWB and Rajasthan Ground Water Department, Dynamic Ground Water Resources (31.03.2023, Annexure IV)

## Split
train 2005-2020, validation 2021, test 2022-2023. Test ke saare stations train mein bhi hain, isliye naye station ka test GroupKFold (SITE_ID) se alag se hota hai.

## Kaise chalayein
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
Saari scripts project root se chalao (`python scripts\<naam>.py`), kyunki paths relative hain.

## Rules
- WELL_DEPTH, LEVEL_DIFF aur target kabhi feature nahi.
- Koi bhi average ya normal sirf training years se.
- Suspicious rows flag hoti hain, delete nahi (scripts/qc_flags.py).

## Known limitations
docs/LIMITATIONS.md dekho.
