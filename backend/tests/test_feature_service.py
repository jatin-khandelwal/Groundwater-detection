from __future__ import annotations

import sqlite3

from backend.app.db import SCHEMA
from backend.app.services.feature_service import FeatureService


def make_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    stations = [
        ("T", "target", "Ajmer", "A", 26.0, 74.0, 400.0, None),
        ("N1", "n1", "Ajmer", "A", 26.01, 74.0, 401.0, None),
        ("N2", "n2", "Ajmer", "A", 26.02, 74.0, 402.0, None),
        ("N3", "n3", "Ajmer", "A", 26.03, 74.0, 403.0, None),
        ("N4", "n4", "Ajmer", "A", 26.04, 74.0, 404.0, None),
        ("N5", "n5", "Ajmer", "A", 26.05, 74.0, 405.0, None),
        ("N6", "n6", "Ajmer", "A", 26.06, 74.0, 406.0, None),
    ]
    conn.executemany("INSERT INTO stations VALUES (?,?,?,?,?,?,?,?)", stations)
    conn.executemany("INSERT INTO readings VALUES (?,?,?,?,?)", [
        ("N1", "2023-05-01", 10.0, 2023, 5),
        ("N1", "2024-05-01", 999.0, 2024, 5),
        ("N2", "2023-05-01", 20.0, 2023, 5),
        # N3 and N4 have no prior readings; N6 must not replace them.
        ("N5", "2023-05-01", 50.0, 2023, 5),
        ("N6", "2023-05-01", 600.0, 2023, 5),
    ])
    conn.commit()
    conn.close()


def test_neighbor_uses_strictly_prior_reading_and_first_five_only(tmp_path):
    db = tmp_path / "test.sqlite3"
    make_db(db)
    built, warnings = FeatureService(db).build(
        district_name=None, block_name=None, site_id="T", latitude=None, longitude=None,
        year=2024, month=5,
    )
    f = built["features"]
    assert f["neighbor_prev_level_count_5"] == 3
    assert f["neighbor_prev_level_mean_5_m"] == (10 + 20 + 50) / 3
    assert built["neighbor_rule"]["source_latest_date"] == "2023-05-01"
    assert f["neighbor_prev_level_mean_5_m"] != (999 + 20 + 50) / 3
    assert not any("future" in warning.lower() for warning in warnings)


def test_no_prior_neighbor_returns_null_mean_and_distance(tmp_path):
    db = tmp_path / "test.sqlite3"
    make_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM readings")
    built, warnings = FeatureService(db).build(
        district_name=None, block_name=None, site_id="T", latitude=None, longitude=None,
        year=2005, month=1,
    )
    f = built["features"]
    assert f["neighbor_prev_level_count_5"] == 0
    assert f["neighbor_prev_level_mean_5_m"] is None
    assert f["nearest_neighbor_prev_distance_km"] is None
    assert warnings


def test_exact_frozen_feature_contract():
    expected = {
        "DISTRICT_NAME", "LAT", "LON", "YEAR", "month_sin", "month_cos", "elevation_m",
        "neighbor_prev_level_mean_5_m", "nearest_neighbor_prev_distance_km", "neighbor_prev_level_count_5",
    }
    import json
    from backend.app.config import FEATURE_LIST_PATH
    assert set(json.loads(FEATURE_LIST_PATH.read_text(encoding="utf-8"))) == expected
