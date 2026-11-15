from __future__ import annotations

import csv

from backend.app.db import initialize_database, connect


def write_csv(path, headers, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_csv_loader_merges_station_metadata_and_observations(tmp_path):
    paths = {name: tmp_path / f"{name}.csv" for name in
             ("stations", "station_blocks", "elevations", "readings", "rainfall", "block_stats")}
    write_csv(paths["stations"], ["SITE_ID", "station_name", "district_name", "latitude", "longitude", "WELL_DEPTH"], [
        {"SITE_ID": "001", "station_name": "Well A", "district_name": "Ajmer", "latitude": "26.0", "longitude": "74.0", "WELL_DEPTH": "90"},
    ])
    write_csv(paths["station_blocks"], ["SITE_ID", "BLOCK_NAME", "BLOCK_STATUS"], [
        {"SITE_ID": "001", "BLOCK_NAME": "Ajmer_Urban", "BLOCK_STATUS": "MATCHED"},
    ])
    write_csv(paths["elevations"], ["SITE_ID", "latitude", "longitude", "elevation_m"], [
        {"SITE_ID": "001", "latitude": "26.0", "longitude": "74.0", "elevation_m": "400"},
    ])
    write_csv(paths["readings"], ["SITE_ID", "DATE", "WLS_WTR_LEVEL", "YEAR", "MONTH"], [
        {"SITE_ID": "001", "DATE": "2023-05-01", "WLS_WTR_LEVEL": "12", "YEAR": "2023", "MONTH": "5"},
    ])
    write_csv(paths["rainfall"], ["lat_grid", "lon_grid", "date", "rainfall_mm"], [
        {"lat_grid": "26.0", "lon_grid": "74.0", "date": "2023-05-01", "rainfall_mm": "0"},
    ])
    write_csv(paths["block_stats"], ["DISTRICT_NAME", "BLOCK_NAME", "STAGE_EXTRACTION_PCT", "CATEGORY_CODE", "ASSESSMENT_YEAR", "ASSESSMENT_DATE"], [
        {"DISTRICT_NAME": "Ajmer", "BLOCK_NAME": "Ajmer_Urban", "STAGE_EXTRACTION_PCT": "120", "CATEGORY_CODE": "OE", "ASSESSMENT_YEAR": "2023", "ASSESSMENT_DATE": "2023-03-31"},
    ])
    db = tmp_path / "groundwater.sqlite3"
    counts = initialize_database(db, paths)
    assert counts == {"stations": 1, "readings": 1, "rainfall_monthly": 1, "block_stats": 1}
    with connect(db) as conn:
        station = conn.execute("SELECT * FROM stations WHERE site_id='001'").fetchone()
        assert station["block_name"] == "Ajmer_Urban"
        assert station["elevation_m"] == 400
        assert station["well_depth_m"] == 90
