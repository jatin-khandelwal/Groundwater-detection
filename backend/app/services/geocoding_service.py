from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from ..config import GEOCODER_URL, GEOCODER_USER_AGENT
from ..db import connect
from .feature_service import haversine_km


RAJASTHAN_BOUNDS = (23.0, 30.5, 69.0, 78.5)
NOMINATIM_ATTRIBUTION = "© OpenStreetMap contributors · Place search via Nominatim"
_CACHE_TTL_SECONDS = 90 * 24 * 60 * 60
_MIN_REQUEST_INTERVAL_SECONDS = 1.05


def _normalize_query(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


class GeocodingService:
    """Resolve one user-submitted place name at a time, cache it, and throttle Nominatim."""

    def __init__(self, db_path):
        self.db_path = db_path

    def _cached(self, query: str) -> list[dict[str, Any]] | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT results_json,cached_at FROM geocode_cache WHERE query=?", (query,)
            ).fetchone()
        if row is None:
            return None
        cached_at = datetime.fromisoformat(row["cached_at"]).replace(tzinfo=timezone.utc)
        age = time.time() - cached_at.timestamp()
        if age > _CACHE_TTL_SECONDS:
            return None
        return json.loads(row["results_json"])

    def _reserve_request_slot(self) -> None:
        # SQLite coordinates the limit across multiple backend workers using this DB.
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT last_request_at FROM geocoder_state WHERE key='nominatim'"
            ).fetchone()
            now = time.time()
            if row is not None:
                delay = _MIN_REQUEST_INTERVAL_SECONDS - (now - float(row["last_request_at"]))
                if delay > 0:
                    time.sleep(delay)
                    now = time.time()
            conn.execute(
                "INSERT INTO geocoder_state(key,last_request_at) VALUES('nominatim',?) "
                "ON CONFLICT(key) DO UPDATE SET last_request_at=excluded.last_request_at",
                (now,),
            )
            conn.commit()

    def _canonical_district(self, address: dict[str, Any], lat: float, lon: float) -> tuple[str, str]:
        possible_names = [
            address.get("state_district"), address.get("county"), address.get("district"),
            address.get("city_district"), address.get("municipality"), address.get("city"),
        ]
        with connect(self.db_path) as conn:
            rows = conn.execute("SELECT DISTINCT district_name FROM stations ORDER BY district_name").fetchall()
            districts = {row[0].casefold(): row[0] for row in rows}
            for name in possible_names:
                if name and name.casefold() in districts:
                    return districts[name.casefold()], "geocoder_admin_area"

            candidates = conn.execute(
                "SELECT district_name,latitude,longitude FROM stations "
                "WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
            ).fetchall()
        if not candidates:
            raise LookupError("No groundwater stations with coordinates are available.")
        closest = min(candidates, key=lambda row: haversine_km(lat, lon, row["latitude"], row["longitude"]))
        return closest["district_name"], "nearest_station_admin_area"

    def search(self, raw_query: str) -> list[dict[str, Any]]:
        query = _normalize_query(raw_query)
        if len(query) < 3:
            raise ValueError("Enter at least 3 characters for a place search.")
        if len(query) > 200:
            raise ValueError("Place search must be 200 characters or fewer.")

        cached = self._cached(query)
        if cached is not None:
            return cached

        self._reserve_request_slot()
        # Another worker may have completed the same search while this request waited.
        cached = self._cached(query)
        if cached is not None:
            return cached

        try:
            response = httpx.get(
                GEOCODER_URL,
                params={
                    "q": f"{raw_query.strip()}, Rajasthan, India",
                    "format": "jsonv2",
                    "addressdetails": 1,
                    "limit": 5,
                    "countrycodes": "in",
                    "viewbox": "69,30.5,78.5,23",
                    "bounded": 1,
                },
                headers={"User-Agent": GEOCODER_USER_AGENT},
                timeout=httpx.Timeout(8.0, connect=3.0),
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError(f"Place search is temporarily unavailable: {exc}") from exc

        results = []
        for item in payload:
            try:
                lat, lon = float(item["lat"]), float(item["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (RAJASTHAN_BOUNDS[0] <= lat <= RAJASTHAN_BOUNDS[1]
                    and RAJASTHAN_BOUNDS[2] <= lon <= RAJASTHAN_BOUNDS[3]):
                continue
            address = item.get("address") or {}
            state = str(address.get("state") or "").casefold()
            if state and state not in {"rajasthan", "राजस्थान"}:
                continue
            try:
                district, district_source = self._canonical_district(address, lat, lon)
            except LookupError:
                continue
            results.append({
                "label": item.get("display_name") or raw_query.strip(),
                "latitude": lat,
                "longitude": lon,
                "district_name": district,
                "district_source": district_source,
                "location_type": item.get("type"),
                "osm_type": item.get("osm_type"),
                "osm_id": item.get("osm_id"),
                "attribution": NOMINATIM_ATTRIBUTION,
            })

        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO geocode_cache(query,results_json,cached_at) VALUES(?,?,CURRENT_TIMESTAMP) "
                "ON CONFLICT(query) DO UPDATE SET results_json=excluded.results_json,cached_at=CURRENT_TIMESTAMP",
                (query, json.dumps(results, ensure_ascii=False)),
            )
            conn.commit()
        return results
