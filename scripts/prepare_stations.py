
import pandas as pd
from pathlib import Path

PROJECT_DIR = Path(r"C:\Ground water")

input_file = PROJECT_DIR / "data" / "raw" / "CGWB - Changes in Depth to Water Level_Filtered_Data.csv"
output_file = PROJECT_DIR / "data" / "processed" / "stations_for_rainfall.csv"

df = pd.read_csv(input_file)

station_name = "Station Name (station_name)"
latitude = "Latitude (latitude)"
longitude = "Longitude (longitude)"

stations = df[[station_name, latitude, longitude]].drop_duplicates()
stations = stations.sort_values([station_name, latitude, longitude])

output_file.parent.mkdir(parents=True, exist_ok=True)
stations.to_csv(output_file, index=False)

print("Unique station locations:", len(stations))
print("Saved to:", output_file)
print(stations.head().to_string(index=False))
