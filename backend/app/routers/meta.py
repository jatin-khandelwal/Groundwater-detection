from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Request

from ..db import connect

router = APIRouter(tags=["metadata"])


@router.get("/health")
def health(request: Request):
    model = request.app.state.model_service
    db_ready = request.app.state.database_ready
    return {"status": "ok" if model.loaded and db_ready else "degraded",
            "model_loaded": model.loaded, "database_ready": db_ready,
            "model_version": model.metrics.get("model_version", "v2"), "model_error": model.error}


@router.get("/districts")
def districts(request: Request):
    try:
        with connect(request.app.state.db_path) as conn:
            rows = conn.execute("SELECT DISTINCT district_name FROM stations WHERE district_name<>'' ORDER BY district_name").fetchall()
        return {"districts": [row[0] for row in rows]}
    except Exception as exc:
        raise HTTPException(503, f"Database unavailable: {exc}") from exc


@router.get("/blocks")
def blocks(district: str, request: Request):
    with connect(request.app.state.db_path) as conn:
        exists = conn.execute("SELECT 1 FROM stations WHERE district_name=? COLLATE NOCASE LIMIT 1", (district,)).fetchone()
        if not exists:
            raise HTTPException(404, f"Unknown district: {district}")
        rows = conn.execute(
            "SELECT DISTINCT block_name FROM stations WHERE district_name=? COLLATE NOCASE AND block_name IS NOT NULL ORDER BY block_name",
            (district,),
        ).fetchall()
    return {"district": district, "blocks": [row[0] for row in rows]}


@router.get("/stations")
def stations(request: Request, district: str | None = None, block: str | None = None,
             as_of_date: date = date(2023, 12, 31), limit: int = 1000):
    if not 1 <= limit <= 5000:
        raise HTTPException(422, "limit must be from 1 to 5000")
    clauses, params = [], []
    if district:
        clauses.append("s.district_name=? COLLATE NOCASE")
        params.append(district)
    if block:
        clauses.append("s.block_name=? COLLATE NOCASE")
        params.append(block)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with connect(request.app.state.db_path) as conn:
        rows = conn.execute(
            "SELECT s.site_id,s.station_name,s.district_name,s.block_name,s.latitude,s.longitude,s.elevation_m,"
            "(SELECT r.level_m FROM readings r WHERE r.site_id=s.site_id AND r.level_m IS NOT NULL AND r.date<=? ORDER BY r.date DESC LIMIT 1) AS latest_level_m,"
            "(SELECT r.date FROM readings r WHERE r.site_id=s.site_id AND r.level_m IS NOT NULL AND r.date<=? ORDER BY r.date DESC LIMIT 1) AS latest_date,"
            "(SELECT bs.stage_pct FROM block_stats bs WHERE bs.district_name=s.district_name COLLATE NOCASE AND bs.block_name=s.block_name COLLATE NOCASE ORDER BY bs.assessment_year DESC LIMIT 1) AS block_stage_pct,"
            "(SELECT bs.category_code FROM block_stats bs WHERE bs.district_name=s.district_name COLLATE NOCASE AND bs.block_name=s.block_name COLLATE NOCASE ORDER BY bs.assessment_year DESC LIMIT 1) AS block_stage_category "
            "FROM stations s" + where + " ORDER BY s.district_name,s.station_name LIMIT ?",
            [as_of_date.isoformat(), as_of_date.isoformat()] + params + [limit]
        ).fetchall()
    return {"count": len(rows), "as_of_date": as_of_date.isoformat(), "stations": [dict(row) for row in rows]}


@router.get("/model/info")
def model_info(request: Request):
    model = request.app.state.model_service
    if not model.loaded:
        raise HTTPException(503, f"Frozen model unavailable: {model.error}")
    return {"model_version": model.metrics.get("model_version", "v2"),
            "dataset": model.metrics.get("dataset"), "features": model.features,
            "validation": model.metrics.get("train_cv_final10", {}),
            "temporal_test": model.metrics.get("test", {}),
            "temporal_test_scope": "2022-2023, stations seen during training; not new-location accuracy",
            "interval_calibration": "saved calibration uses previous stored neighbor inputs; neighbor_v3 recalibration not performed",
            "risk_thresholds_m": model.metrics.get("risk_thresholds_m", [8, 22]),
            "confidence_rule": model.metrics.get("confidence_rule")}
