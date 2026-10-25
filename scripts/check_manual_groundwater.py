
import pandas as pd
from pathlib import Path

ROOT = Path(r"C:\Ground water")

MATCH_FILE = ROOT / "data" / "processed" / "manual_groundwater_station_matches.csv"
REFERENCE_FILE = ROOT / "data" / "raw" / "CGWB - Changes in Depth to Water Level_Filtered_Data.csv"

def main():
    manual = pd.read_csv(MATCH_FILE, low_memory=False)
    ref = pd.read_csv(REFERENCE_FILE, low_memory=False)

    # Reference station coordinates and names
    ref["lat_round"] = pd.to_numeric(
        ref["Latitude (latitude)"], errors="coerce"
    ).round(3)
    ref["lon_round"] = pd.to_numeric(
        ref["Longitude (longitude)"], errors="coerce"
    ).round(3)

    manual["lat_round"] = pd.to_numeric(
        manual["latitude"], errors="coerce"
    ).round(3)
    manual["lon_round"] = pd.to_numeric(
        manual["longitude"], errors="coerce"
    ).round(3)

    ref_locations = ref[
        ["Station Name (station_name)", "lat_round", "lon_round"]
    ].drop_duplicates()

    manual_locations = manual[
        ["station_name", "station_code", "lat_round", "lon_round"]
    ].drop_duplicates()

    result = manual_locations.merge(
        ref_locations,
        on=["lat_round", "lon_round"],
        how="left",
        indicator=True
    )

    print("Manual unique station-code/location combinations:",
          len(manual_locations))
    print("Coordinate matches:", (result["_merge"] == "both").sum())
    print("Unmatched combinations:", (result["_merge"] == "left_only").sum())

    print("\nSample unmatched stations:")
    print(
        result[result["_merge"] == "left_only"]
        [["station_name", "station_code", "lat_round", "lon_round"]]
        .head(20)
        .to_string(index=False)
    )

if __name__ == "__main__":
    main()
