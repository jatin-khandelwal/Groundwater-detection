from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request

from ..config import ADVISORY_BUFFER_M
from ..db import connect
from ..schemas import AdvisoryRequest
from ..services.advisory_service import AdvisoryService
from ..services.feature_service import FeatureService

router = APIRouter(tags=["advisory"])


@router.post("/advisory")
def advisory(body: AdvisoryRequest, request: Request):
    model = request.app.state.model_service
    try:
        predicted = None
        if model.loaded:
            built, _ = FeatureService(request.app.state.db_path).build(
                district_name=body.district_name, block_name=body.block_name, site_id=None,
                latitude=None, longitude=None, year=body.year, month=body.month,
            )
            predicted = model.predict(built["features"])
        result = AdvisoryService(request.app.state.db_path, ADVISORY_BUFFER_M).build(
            body.district_name, body.block_name, predicted, body.year,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc

    with connect(request.app.state.db_path) as conn:
        conn.execute("INSERT INTO prediction_log(endpoint,request_json,response_json) VALUES(?,?,?)",
                     ("/advisory", body.model_dump_json(), json.dumps(result, allow_nan=False)))
        conn.commit()
    return result
