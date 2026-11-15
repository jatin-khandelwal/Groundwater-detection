from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..db import connect


class AdvisoryService:
    """Historical-depth summary with explicit sample-size/fallback labels."""

    def __init__(self, db_path, buffer_m: float | None = None):
        self.db_path = db_path
        self.buffer_m = buffer_m

    def build(self, district_name: str, block_name: str, predicted_level_m: float | None,
              requested_year: int) -> dict[str, Any]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT well_depth_m FROM stations WHERE district_name=? COLLATE NOCASE AND block_name=? COLLATE NOCASE AND well_depth_m IS NOT NULL AND well_depth_m>0",
                (district_name, block_name),
            ).fetchall()
            source = "block"
            if len(rows) < 3:
                rows = conn.execute(
                    "SELECT well_depth_m FROM stations WHERE district_name=? COLLATE NOCASE AND well_depth_m IS NOT NULL AND well_depth_m>0",
                    (district_name,),
                ).fetchall()
                source = "district"
            depths = sorted(float(row["well_depth_m"]) for row in rows)
            if not depths:
                raise LookupError("No usable historical WELL_DEPTH records for this block or district")

            stage = conn.execute(
                "SELECT stage_pct,category_code,assessment_year FROM block_stats WHERE district_name=? COLLATE NOCASE AND block_name=? COLLATE NOCASE AND assessment_year<=? ORDER BY assessment_year DESC LIMIT 1",
                (district_name, block_name, requested_year),
            ).fetchone()

        median = _percentile(depths, 0.5)
        p75 = _percentile(depths, 0.75)
        spread = depths[-1] - depths[0]
        if source == "block" and len(depths) >= 10 and spread <= 30:
            confidence = "high"
        elif source == "block" and len(depths) >= 3:
            confidence = "medium"
        else:
            confidence = "low"

        recommended = p75
        method = "historical WELL_DEPTH 75th percentile (provisional)"
        if self.buffer_m is not None and predicted_level_m is not None:
            recommended = max(recommended, predicted_level_m + self.buffer_m)
            method = "max(historical WELL_DEPTH p75, predicted water level + configured buffer)"

        warnings = ["Historical WELL_DEPTH is a reference distribution, not a geotechnical or drilling safety guarantee."]
        if self.buffer_m is None:
            warnings.append("No supervisor-approved borewell buffer is configured; recommended depth uses historical p75 only.")
        if source == "district":
            warnings.append("Fewer than 3 usable well depths were available in this block; district data was used.")
        if stage is None:
            warnings.append("No block extraction-stage assessment at or before the requested year was found.")
        elif (stage["category_code"] or "").upper() == "OE" or (stage["stage_pct"] is not None and stage["stage_pct"] > 100):
            warnings.append("Block is marked over-exploited / extraction stage exceeds 100% in the latest available assessment.")

        return {
            "district_name": district_name,
            "block_name": block_name,
            "recommended_depth_m": round(recommended, 2),
            "method": method,
            "historical_well_depth": {"count": len(depths), "median_m": round(median, 2),
                                      "p75_m": round(p75, 2), "min_m": round(depths[0], 2),
                                      "max_m": round(depths[-1], 2), "spread_m": round(spread, 2),
                                      "source_level": source},
            "confidence": confidence,
            "predicted_water_level_m": round(predicted_level_m, 2) if predicted_level_m is not None else None,
            "buffer_m": self.buffer_m,
            "extraction_stage": {
                "stage_pct": round(float(stage["stage_pct"]), 2) if stage and stage["stage_pct"] is not None else None,
                "category": stage["category_code"] if stage else None,
                "assessment_year": stage["assessment_year"] if stage else None,
            },
            "warnings": warnings,
        }


def _percentile(values: list[float], q: float) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * q
    lo, hi = int(position), min(int(position) + 1, len(values) - 1)
    fraction = position - lo
    return values[lo] * (1 - fraction) + values[hi] * fraction
