from __future__ import annotations

import math
import sqlite3
from datetime import date
from typing import Any

from ..db import connect


EARTH_KM = 6371.0088
K_NEIGHBORS = 5
RADIUS_KM = 40.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return EARTH_KM * 2 * math.asin(math.sqrt(min(1.0, a)))


class FeatureService:
    def __init__(self, db_path):
        self.db_path = db_path

    def resolve_target(self, *, district_name: str | None, block_name: str | None,
                       site_id: str | None, latitude: float | None, longitude: float | None) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            if site_id:
                row = conn.execute("SELECT * FROM stations WHERE site_id=?", (site_id,)).fetchone()
                if row is None:
                    raise LookupError(f"Unknown site_id: {site_id}")
                if district_name and row["district_name"].casefold() != district_name.casefold():
                    raise ValueError("site_id does not belong to district_name")
                if row["latitude"] is None or row["longitude"] is None:
                    raise LookupError(f"Station {site_id} has no usable coordinates")
                return self._target_from_row(row, "station")

            if latitude is not None and longitude is not None:
                if not district_name:
                    raise ValueError("district_name is required when coordinates are supplied")
                district = conn.execute(
                    "SELECT district_name FROM stations WHERE district_name=? COLLATE NOCASE LIMIT 1", (district_name,)
                ).fetchone()
                if district is None:
                    raise LookupError(f"Unknown district: {district_name}")
                canonical_district = district["district_name"]
                return {"site_id": None, "district_name": canonical_district, "block_name": block_name,
                        "latitude": latitude, "longitude": longitude, "elevation_m": self._nearest_elevation(conn, latitude, longitude, district_name),
                        "location_source": "request_coordinates"}

            if not district_name:
                raise ValueError("Provide district_name, site_id, or latitude and longitude")
            where = ["district_name = ? COLLATE NOCASE", "latitude IS NOT NULL", "longitude IS NOT NULL"]
            params: list[Any] = [district_name]
            if block_name:
                where.append("block_name = ? COLLATE NOCASE")
                params.append(block_name)
            rows = conn.execute(
                "SELECT * FROM stations WHERE " + " AND ".join(where) + " ORDER BY site_id", params
            ).fetchall()
            if not rows and block_name:
                raise LookupError(f"No mapped station coordinates for block '{block_name}' in '{district_name}'")
            if not rows:
                raise LookupError(f"No station coordinates found for district '{district_name}'")
            latitudes = [float(row["latitude"]) for row in rows]
            longitudes = [float(row["longitude"]) for row in rows]
            elevations = [float(row["elevation_m"]) for row in rows if row["elevation_m"] is not None]
            return {"site_id": None, "district_name": rows[0]["district_name"], "block_name": block_name,
                    "latitude": sum(latitudes) / len(latitudes), "longitude": sum(longitudes) / len(longitudes),
                    "elevation_m": sum(elevations) / len(elevations) if elevations else None,
                    "location_source": "mapped_block_station_centroid" if block_name else "district_station_centroid",
                    "centroid_station_count": len(rows)}

    @staticmethod
    def _target_from_row(row: sqlite3.Row, source: str) -> dict[str, Any]:
        return {"site_id": row["site_id"], "district_name": row["district_name"],
                "block_name": row["block_name"], "latitude": row["latitude"], "longitude": row["longitude"],
                "elevation_m": row["elevation_m"], "location_source": source}

    @staticmethod
    def _nearest_elevation(conn, lat: float, lon: float, district: str) -> float | None:
        candidates = conn.execute(
            "SELECT latitude,longitude,elevation_m FROM stations WHERE district_name=? COLLATE NOCASE AND elevation_m IS NOT NULL AND latitude IS NOT NULL AND longitude IS NOT NULL",
            (district,),
        ).fetchall()
        if not candidates:
            return None
        chosen = min(candidates, key=lambda r: haversine_km(lat, lon, r["latitude"], r["longitude"]))
        return float(chosen["elevation_m"])

    def build(self, *, district_name: str | None, block_name: str | None, site_id: str | None,
              latitude: float | None, longitude: float | None, year: int, month: int) -> tuple[dict[str, Any], list[str]]:
        target = self.resolve_target(district_name=district_name, block_name=block_name, site_id=site_id,
                                     latitude=latitude, longitude=longitude)
        target_day = date(year, month, 1).isoformat()
        with connect(self.db_path) as conn:
            stations = conn.execute(
                "SELECT site_id,station_name,district_name,block_name,latitude,longitude FROM stations "
                "WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
            ).fetchall()
            candidates = []
            for station in stations:
                sid = station["site_id"]
                if target["site_id"] is not None and sid == target["site_id"]:
                    continue
                distance = haversine_km(target["latitude"], target["longitude"], station["latitude"], station["longitude"])
                if distance <= RADIUS_KM:
                    candidates.append((distance, sid))
            candidates.sort(key=lambda item: (item[0], item[1]))

            values, contributing_distances, source_dates, neighbor_stations = [], [], [], []
            # Select K nearest stations before checking whether a prior reading exists.
            for distance, sid in candidates[:K_NEIGHBORS]:
                reading = conn.execute(
                    "SELECT date,level_m FROM readings WHERE site_id=? AND date<? AND level_m IS NOT NULL ORDER BY date DESC LIMIT 1",
                    (sid, target_day),
                ).fetchone()
                station = next(item for item in stations if item["site_id"] == sid)
                station_info = {
                    "site_id": sid,
                    "station_name": station["station_name"],
                    "district_name": station["district_name"],
                    "block_name": station["block_name"],
                    "distance_km": round(distance, 3),
                    "reading_date": reading["date"] if reading else None,
                    "level_m": float(reading["level_m"]) if reading else None,
                    "contributed_to_model": reading is not None,
                }
                neighbor_stations.append(station_info)
                if reading is not None:
                    values.append(float(reading["level_m"]))
                    contributing_distances.append(distance)
                    source_dates.append(reading["date"])

        mean = sum(values) / len(values) if values else None
        nearest = min(contributing_distances) if contributing_distances else None
        features = {
            "DISTRICT_NAME": target["district_name"],
            "LAT": float(target["latitude"]),
            "LON": float(target["longitude"]),
            "YEAR": int(year),
            "month_sin": math.sin(2 * math.pi * month / 12),
            "month_cos": math.cos(2 * math.pi * month / 12),
            "elevation_m": target["elevation_m"],
            "neighbor_prev_level_mean_5_m": mean,
            "nearest_neighbor_prev_distance_km": nearest,
            "neighbor_prev_level_count_5": len(values),
        }
        warnings = []
        if not values:
            warnings.append("No eligible neighbor readings; neighbor mean and distance are null and confidence is low.")
        if target["elevation_m"] is None:
            warnings.append("Elevation unavailable; the frozen model imputer will handle the missing value.")
        if source_dates and (date(year, month, 1) - date.fromisoformat(min(source_dates))).days > 365:
            warnings.append("At least one contributing reading is older than one year; no maximum-age cutoff is defined.")
        if year > 2023:
            warnings.append("Prediction year is beyond the model's 2005-2023 modeling window; year extrapolation is limited.")
        return {"features": features, "target": target, "neighbor_stations": neighbor_stations,
                "neighbor_rule": {"k": K_NEIGHBORS, "radius_km_inclusive": RADIUS_KM,
                                  "selection": "nearest-first before reading availability check",
                                  "reading_rule": "latest reading strictly before the first day of target month; no age limit",
                                  "contributing_site_count": len(values), "source_latest_date": max(source_dates) if source_dates else None}}, warnings
