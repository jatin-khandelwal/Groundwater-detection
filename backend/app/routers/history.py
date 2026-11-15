from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Request

from ..services.history_service import HistoryService

router = APIRouter(tags=["history"])


@router.get("/history")
def history(request: Request, site_id: str | None = None, district: str | None = None,
            block: str | None = None, start_date: date | None = None, end_date: date | None = None):
    if not site_id and not district:
        raise HTTPException(422, "Provide site_id or district")
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, "start_date must be before or equal to end_date")
    try:
        return HistoryService(request.app.state.db_path).history(
            district_name=district, block_name=block, site_id=site_id,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
