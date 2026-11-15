from __future__ import annotations

from typing import Any

from ..db import connect
from .feature_service import FeatureService, haversine_km


class HistoryService:
    def __init__(self, db_path):
        self.db_path = db_path
        self.features = FeatureService(db_path)

    def history(self, *, district_name: str | None, block_name: str | None, site_id: str | None,
                start_date: str | None, end_date: str | None) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            if site_id:
                station = conn.execute("SELECT * FROM stations WHERE site_id=?", (site_id,)).fetchone()
                if not station:
                    raise LookupError(f"Unknown site_id: {site_id}")
                where = "r.site_id=?"
                params: list[Any] = [site_id]
                title = station["station_name"] or site_id
                lat, lon = station["latitude"], station["longitude"]
                readings = conn.execute(
                    "SELECT date,level_m FROM readings r WHERE " + where + _date_clauses(start_date, end_date),
                    params + _date_params(start_date, end_date),
                ).fetchall()
            else:
                if not district_name:
                    raise ValueError("Provide site_id or district_name")
                target = self.features.resolve_target(district_name=district_name, block_name=block_name,
                                                      site_id=None, latitude=None, longitude=None)
                lat, lon = target["latitude"], target["longitude"]
                where = "s.district_name=? COLLATE NOCASE"
                params = [district_name]
                if block_name:
                    where += " AND s.block_name=? COLLATE NOCASE"
                    params.append(block_name)
                readings = conn.execute(
                    "SELECT r.date,AVG(r.level_m) AS level_m FROM readings r JOIN stations s ON s.site_id=r.site_id WHERE "
                    + where + _date_clauses(start_date, end_date, "r") + " GROUP BY r.date ORDER BY r.date",
                    params + _date_params(start_date, end_date),
                ).fetchall()
                title = f"{district_name}" + (f" / {block_name}" if block_name else "")

            rainfall = []
            if lat is not None and lon is not None:
                grids = conn.execute("SELECT DISTINCT lat_grid,lon_grid FROM rainfall_monthly").fetchall()
                if grids:
                    grid = min(grids, key=lambda r: haversine_km(lat, lon, r["lat_grid"], r["lon_grid"]))
                    rainfall = conn.execute(
                        "SELECT date,rainfall_mm FROM rainfall_monthly WHERE lat_grid=? AND lon_grid=?" +
                        _date_clauses(start_date, end_date) + " ORDER BY date",
                        (grid["lat_grid"], grid["lon_grid"]) + tuple(_date_params(start_date, end_date)),
                    ).fetchall()
                    grid_info = {"lat": grid["lat_grid"], "lon": grid["lon_grid"]}
                else:
                    grid_info = None
            else:
                grid_info = None

        return {"series": title,
                "water_levels": [{"date": row["date"], "level_m": row["level_m"]} for row in readings],
                "rainfall_grid": grid_info,
                "rainfall": [{"date": row["date"], "rainfall_mm": row["rainfall_mm"]} for row in rainfall],
                "unit_note": "Water level is depth to water: larger values mean water is deeper below ground."}


def _date_clauses(start: str | None, end: str | None, alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return (f" AND {prefix}date>=?" if start else "") + (f" AND {prefix}date<=?" if end else "")


def _date_params(start: str | None, end: str | None) -> list[str]:
    return ([start] if start else []) + ([end] if end else [])
