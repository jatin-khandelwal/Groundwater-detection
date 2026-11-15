from __future__ import annotations

import json
from statistics import median

from fastapi import APIRouter, HTTPException, Request

from ..db import connect
from ..schemas import PredictRequest
from ..services.feature_service import FeatureService

router = APIRouter(tags=["prediction"])


@router.post("/predict")
def predict(body: PredictRequest, request: Request):
    model = request.app.state.model_service
    if not model.loaded:
        raise HTTPException(503, f"Frozen v2 model unavailable: {model.error}")
    service = FeatureService(request.app.state.db_path)
    try:
        built, warnings = service.build(
            district_name=body.district_name, block_name=body.block_name, site_id=body.site_id,
            latitude=body.latitude, longitude=body.longitude, year=body.year, month=body.month,
        )
        features = built["features"]
        prediction = model.predict(features)
        interval = model.prediction_interval(prediction)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Prediction failed: {type(exc).__name__}: {exc}") from exc

    thresholds = model.metrics.get("risk_thresholds_m", [8, 22])
    if len(thresholds) != 2:
        thresholds = [8, 22]
    risk = "lower" if prediction < thresholds[0] else "moderate" if prediction < thresholds[1] else "higher"
    confidence = interval.get("confidence", "low")
    if features["neighbor_prev_level_count_5"] == 0:
        confidence = "low"
    neighbor_stations = built["neighbor_stations"]
    contributing = [item for item in neighbor_stations if item["contributed_to_model"]]
    neighbor_summary = {
        "count": len(contributing),
        "mean_level_m": round(sum(item["level_m"] for item in contributing) / len(contributing), 2) if contributing else None,
        "median_level_m": round(median(item["level_m"] for item in contributing), 2) if contributing else None,
        "min_level_m": round(min(item["level_m"] for item in contributing), 2) if contributing else None,
        "max_level_m": round(max(item["level_m"] for item in contributing), 2) if contributing else None,
        "nearest_distance_km": round(min(item["distance_km"] for item in contributing), 3) if contributing else None,
        "latest_source_date": max(item["reading_date"] for item in contributing) if contributing else None,
    }
    response = {
        "model_version": model.metrics.get("model_version", "v2"),
        "prediction_m": round(prediction, 2),
        "interval": interval,
        "risk": risk,
        "risk_definition": "Relative depth-to-water band (<8 m, 8-22 m, >=22 m); not a drilling-safety classification.",
        "confidence": confidence,
        "inputs_used": {**features, "location_source": built["target"]["location_source"],
                        "neighbor_rule": built["neighbor_rule"]},
        "nearby_summary": neighbor_summary,
        "nearby_stations": neighbor_stations,
        "warnings": warnings + (["Prediction range is based on old stored neighbor inputs, not recalibrated for neighbor_v3."]
                                 if interval.get("calibration_status", "").startswith("historical_neighbor_inputs") else []),
    }
    with connect(request.app.state.db_path) as conn:
        conn.execute("INSERT INTO prediction_log(endpoint,request_json,response_json) VALUES(?,?,?)",
                     ("/predict", body.model_dump_json(), json.dumps(response, allow_nan=False)))
        conn.commit()
    return response
