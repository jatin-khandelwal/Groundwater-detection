from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.db import SCHEMA
from backend.app.routers import advisory, history, meta, predict


class UnavailableModel:
    loaded = False
    error = "test model unavailable"
    metrics = {"model_version": "v2"}
    features = []


def make_client(db_path):
    import sqlite3
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO stations VALUES (?,?,?,?,?,?,?,?)", ("1", "Well", "Ajmer", "Ajmer_Urban", 26, 74, 400, 80))
    conn.execute("INSERT INTO stations VALUES (?,?,?,?,?,?,?,?)", ("2", "Well 2", "Ajmer", "Ajmer_Urban", 26.01, 74, 401, 90))
    conn.execute("INSERT INTO stations VALUES (?,?,?,?,?,?,?,?)", ("3", "Well 3", "Ajmer", "Other", 26.02, 74, 402, 100))
    conn.execute("INSERT INTO readings VALUES (?,?,?,?,?)", ("1", "2023-11-01", 15, 2023, 11))
    conn.execute("INSERT INTO readings VALUES (?,?,?,?,?)", ("1", "2024-05-01", 999, 2024, 5))
    conn.execute("INSERT INTO block_stats VALUES (?,?,?,?,?,?)", ("Ajmer", "Ajmer_Urban", 120, "OE", 2023, "2023-03-31"))
    conn.commit()
    conn.close()
    test_app = FastAPI()
    test_app.include_router(meta.router)
    test_app.include_router(history.router)
    test_app.include_router(predict.router)
    test_app.include_router(advisory.router)
    test_app.state.db_path = db_path
    test_app.state.database_ready = True
    test_app.state.model_service = UnavailableModel()
    return TestClient(test_app)


def test_meta_routes_and_clean_unknown_district(tmp_path):
    client = make_client(tmp_path / "api.sqlite3")
    assert client.get("/health").json()["database_ready"] is True
    assert client.get("/districts").json() == {"districts": ["Ajmer"]}
    assert client.get("/blocks", params={"district": "Unknown"}).status_code == 404


def test_invalid_month_is_422_and_model_unavailable_is_503(tmp_path):
    client = make_client(tmp_path / "api.sqlite3")
    invalid = client.post("/predict", json={"district_name": "Ajmer", "month": 13, "year": 2024})
    assert invalid.status_code == 422
    unavailable = client.post("/predict", json={"district_name": "Ajmer", "month": 5, "year": 2024})
    assert unavailable.status_code == 503


def test_station_map_defaults_to_pre_holdout_cutoff(tmp_path):
    client = make_client(tmp_path / "api.sqlite3")
    result = client.get("/stations", params={"district": "Ajmer", "block": "Ajmer_Urban"})
    assert result.status_code == 200
    payload = result.json()
    assert payload["as_of_date"] == "2023-12-31"
    assert payload["stations"][0]["latest_date"] == "2023-11-01"
    assert payload["stations"][0]["latest_level_m"] == 15


def test_advisory_district_fallback_and_extraction_warning(tmp_path):
    client = make_client(tmp_path / "api.sqlite3")
    result = client.post("/advisory", json={"district_name": "Ajmer", "block_name": "Ajmer_Urban", "month": 5, "year": 2024})
    assert result.status_code == 200
    payload = result.json()
    assert payload["historical_well_depth"]["source_level"] == "district"
    assert payload["historical_well_depth"]["count"] == 3
    assert payload["extraction_stage"]["category"] == "OE"
    assert payload["recommended_depth_m"] == 95
    assert any("over-exploited" in message for message in payload["warnings"])
