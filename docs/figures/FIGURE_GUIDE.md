# Report figures and source notes

The PNGs in this folder were generated from project code, datasets, and saved result files for use in the B.Tech report. Captions below can be adapted to the department's numbering format. Refer to each inserted figure in the chapter text and cite the underlying data/result source in the references or caption.

| File | Suggested caption and placement | Source and use note |
|---|---|---|
| `Figure_3_1_data_pipeline.png` | **Figure 3.1. Data preparation and modelling workflow.** Chapter 3. | Project README and dataset-building scripts. It distinguishes source/context datasets from the frozen v2 inputs. |
| `Figure_3_2_observation_coverage.png` | **Figure 3.2. Groundwater observation counts by monitoring round, 2005–2023.** Chapter 3. | `data/processed/quality_year_round_counts_v2.csv`. Counts are observations, not unique stations. Near-zero segments mark sparse or missing rounds in the underlying file. |
| `Figure_3_3_station_coordinates.png` | **Figure 3.3. Coordinate distribution of groundwater monitoring stations.** Chapter 3, optional. | `data/processed/station_master.csv`. This is a coordinate scatter plot; it has no district/state boundary and must not be described as an administrative map. |
| `Figure_4_1_application_architecture.png` | **Figure 4.1. Local application architecture.** Chapter 4. | `backend/app`, `frontend/streamlit_app.py`, and `backend/README.md`. Shows the local, non-HTTPS demo and external Nominatim place search. |
| `Figure_4_2_prediction_flow.png` | **Figure 4.2. Request-time location prediction workflow.** Chapter 4. | `backend/app/services/feature_service.py` and `backend/app/routers/predict.py`. State the reconstructed neighbor rule and interval-calibration limitation in the surrounding text. |
| `Figure_4_3_database_relationships.png` | **Figure 4.3. Core SQLite entities and relationships.** Chapter 4. | `backend/app/db.py`. Simplified view; not every support table or column is shown. |
| `Figure_5_1_candidate_model_comparison.png` | **Figure 5.1. Tuned Random Forest and XGBoost candidate MAE on new-station GroupKFold validation.** Chapter 5. | `docs/results/comparison_table.csv`. Both candidates use 26 features. This is not the frozen 10-feature v2 score. |
| `Figure_5_2_feature_ablation.png` | **Figure 5.2. Variant B validation MAE across feature-group ablation steps.** Chapter 5. | `docs/results/ablation_table.csv`. Preliminary candidate feature sequence; explain that it is not the final v2 feature list. |
| `Figure_5_3_permutation_importance.png` | **Figure 5.3. Grouped permutation diagnostic for candidate feature groups.** Chapter 5, optional. | `docs/results/permutation_importance_groups.csv`. Broader groups include inputs absent from frozen v2. Do not label this as final-v2 feature importance or causal evidence. |
| `Figure_5_4_final_model_metrics.png` | **Figure 5.4. Frozen v2 MAE under separate evaluation settings.** Chapter 5. | `models/v2/metrics.json` and `docs/results/holdout_2024_jan_may_v3.json`. The panels intentionally separate unfamiliar-location CV from temporal known-station tests; do not interpret them as the same split. |

## Still to capture from the running application

The local API was not running during this figure task, so no live interface screenshots were taken. Capture clean screenshots of: (1) sign-in page without entered credentials; (2) a user location search and prediction result with nearby-station table; (3) station map; (4) admin user-management page with personal details obscured; and (5) model/data page. These belong in Chapter 4 as implementation evidence. The report guidelines require test cases separately; screenshots do not replace the test-results table.

## Do not add without a source

- A Rajasthan administrative-boundary map requires a verified boundary dataset and attribution. The coordinate plot above is not a substitute.
- Actual-versus-predicted scatter plots or residual distributions require row-level predictions from a documented evaluation split. Do not infer them from aggregate metrics.
- A rainfall graph may describe the collected climate data, but rainfall is not an input to frozen model v2; do not present it as evidence that v2 uses rainfall.
- ROC curves and confusion matrices are not suitable for this continuous regression target.
