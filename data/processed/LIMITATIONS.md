# Data limitations (auto-generated)

- Dataset: 92452 rows, 1403 stations, 33 districts. Modeling window: 2005-2023; 2024 is partial and not used for testing.
- Measurements are seasonal (4 rounds per year: Jan, May, Aug, Nov), so this is a seasonal level prediction, not a daily forecast.
- Block mapping covers only 41.6% of stations; unverified blocks are left missing (not guessed from the nearest station).
- Stage of Extraction is available for 28.9% of stations and comes from a single assessment snapshot (assessment year(s): [2023]); applying it to earlier years is a limitation and is reported with and without the feature.
- Years with no data in the window: none.
- Rounds with fewer than 300 readings: 2012 Aug (1 readings), 2016 Jan (119 readings), 2018 Nov (85 readings), 2020 May (89 readings), 2021 May (83 readings).
- Rainfall is NASA POWER gridded data (0.5 degree), not station rainfall. District normals are simple averages of grid cells, not area-weighted.
- Future rainfall is unknown; predictions use the district normal or a dry/wet scenario.
- Elevation is SRTM30 via a public API at station coordinates; not individually field-verified.
- Direct pumping/abstraction data is not available; Stage of Extraction is only a proxy.
- WELL_DEPTH and LEVEL_DIFF are excluded from model inputs to avoid leakage.
- Data source credit: India Data Portal (CGWB / India-WRIS data), Open Data Commons Attribution License.
