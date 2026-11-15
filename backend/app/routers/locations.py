from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from ..services.geocoding_service import GeocodingService, NOMINATIM_ATTRIBUTION


router = APIRouter(tags=["locations"])


@router.get("/locations/search")
def search_locations(request: Request, q: str = Query(min_length=3, max_length=200)):
    try:
        results = GeocodingService(request.app.state.db_path).search(q)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"query": q, "count": len(results), "attribution": NOMINATIM_ATTRIBUTION,
            "results": results}
