
## 2026-10-27 Step 10: final feature set (test dekhne se PEHLE likha)

Rule: koi group deployed model mein tabhi, jab (1) naye-station CV (GroupKFold(5) by SITE_ID) mein R2 gain >= 0.01
aur (2) Backend use inference par bana sake. Test se koi faisla nahi.

| Group | Ablation gain | Faisla | Wajah |
|---|---|---|---|
| baseline (district, lat, lon, year, month_sin, month_cos) | base | rakho | base model |
| elevation | +0.069 | rakho | rule pass, DB se milta hai |
| neighbor | +0.044 | rakho | rule pass. Backend DB se pichhle observed levels se banayega, door ke mahine ke liye purane, confidence low |
| rainfall | ~+0.005 | nahi | gain < 0.01 |
| well/aquifer | +0.007 | nahi | gain < 0.01, naye borewell ka type pata nahi |
| district stage | ~+0.004 | nahi | gain < 0.01, 2023 snapshot |
| block stage | negative | nahi | 62% missing, score gira |
| climate_extra, evap_soil_extra | +0.002, +0.005 | nahi | gain < 0.01, future ka climate approximate karna padega |
| YEAR | +0.015 | rakho | rule pass. Limitation: 2021 ke baad ke saalon ke liye model flat rahega |

Dashboard: rainfall deployed model mein nahi hai, to dry/normal/wet selector prediction nahi badlega. Selector hatana ya "sirf jaankari" likhna.
## 28 Oct 2026: Final model (freeze se pehle)
- Faisla: Option A, final 10 features (district, lat, lon, year, month_sin, month_cos, elevation, 3 neighbor features). WELL_TYPE nahi.
- Wajah: train par WELL_TYPE ka median level alag hai (tube well 37.4 m, dug well 10.0 m, bore well 7.2 m, piezometer 48.4 m, slim hole 3.2 m), yaani type khud gehrai se juda hai, DEPTH jaisa ishara. Naye borewell ke liye ye input ka matlab nahi, aur Unknown bhejne par model final(10) se bhi kharab ho jata hai.
- Neighbor check (train, naye-station CV, final 10): saari rows MAE 7.531 / R2 0.6902; distance == 0 (1,409 rows, 2.8%) MAE 4.555 / R2 0.8103; distance > 0 (48,633 rows) MAE 7.598 / R2 0.6876; distance NaN (321 rows) MAE 10.429 / R2 0.2698. Koi badlav nahi, par neighbor na ho to confidence low.
- Rainfall, climate, stage, aquifer deployed model mein nahi (naye station aur naye district CV mein gain rule se kam ya nuksan). Dashboard ka dry/normal/wet selector prediction nahi badlega, isliye hataya jayega.
- YEAR rakha (ablation mein +0.015), Limitation: future saal par tree flat rehta hai.
- Risk thresholds 8 m aur 22 m (train target ke 33rd aur 66th percentile). Confidence: range width 15 m se kam high, 15 se 30 medium, 30 se zyada low.
- Test protocol: test (2022-2023) freeze ke baad sirf ek baar. Chahe jaisa aaye, report hoga, koi dobara tuning nahi.

## 2026-10-28 Freeze: test result (final 10 features, train + val par fit)
- Test (2022-2023, 5,178 rows): R2 0.9411, MAE 3.205, MedAE 2.067. Neighbor distance > 0 (5,005 rows): R2 0.9430, MAE 3.224, MedAE 2.078.
- Interval coverage 0.943 (target 0.80), mean width 22.53 m. Range naye-station residuals se bani thi, purane stations par zyada coverage deti hai.
- Ye "naya saal, purane stations" ka number hai (test ke saare 934 stations train mein bhi hain), naye location ka nahi.
- Naye location ke honest numbers train CV se: naya station R2 0.6902 / MAE 7.531, naya district R2 0.5868 / MAE 9.037.
- Persistence test: R2 0.9403, MAE 2.648. Result chahe jaisa aaya, koi dobara tuning nahi kiya.

## 2026-10-29: Reconstructed neighbor rule and train-only CV gate

- Original code that generated the stored neighbor columns was not recovered. The operational rule below is a documented reconstruction, not a claim that the historical generator was found.
- Rule used for `neighbor_v3.csv`: exclude the target `SITE_ID`; select up to the 5 nearest other stations within 40 km, nearest-first, before checking reading availability; for each selected station use its latest reading strictly before the target date; no age cutoff; do not replace a selected station with the sixth-nearest if it has no prior reading. Mean and nearest contributing-station distance are NaN when count is zero; count is 0.
- Leakage assertion passed for the rebuilt table: every source reading date is strictly earlier than its target date (minimum gap 1 day). This verifies the reconstruction's timing, not the unrecovered historical generator.
- Comparison with stored features: among 87,980 rows with both means available, median and 90th-percentile absolute mean difference were 0.0 m; count agreed on 97.8% of rows. The remaining count/mean mismatches are unresolved; coordinate tie ordering is only a hypothesis.
- Predeclared gate: retain the frozen model if new-station GroupKFold(5) changes by no more than 0.01 R2 and 0.1 m MAE. Stored-feature baseline was R2 0.6902 / MAE 7.531 m; reconstructed features scored R2 0.6941 / MAE 7.501 m. Gate passed.
- New-district leave-one-district-out comparison: baseline R2 0.5868 / MAE 9.037 m; reconstructed R2 0.5815 / MAE 9.104 m. Both deltas are within 0.01 R2 and 0.1 m MAE.
- Decision: keep the frozen ten-feature v2 model; do not retune or reopen the 2022-2023 test. The saved interval calibration and old temporal-test score remain based on the previous stored neighbor columns and were not recalculated for v3 inputs.
- Detailed metrics: `docs/results/neighbor_v3_cv.json`. The checked-in `scripts/build_neighbor_v3.py` is an offline rebuild/audit script; backend request-time implementation must follow the rule above and compare its outputs against `data/processed/neighbor_v3.csv`.

## 2026-10-29: Pre-registered 2024 Jan/May holdout for reconstructed neighbors

- Purpose: one-time temporal evaluation of the frozen v2 model using the reconstructed neighbor rule, because the 2022-2023 test and saved interval calibration use the older stored neighbor columns.
- Holdout rows: `YEAR == 2024` and `MONTH in {1, 5}` from `data/processed/dataset_v2_neighbors.csv`. The file currently contains 668 January rows and 74 May rows (742 total); August is excluded.
- Protocol: evaluate the frozen v2 model once after the request-time neighbor implementation is available. Report MAE, RMSE, and R2 for the combined holdout and separately for stations seen in model training versus unseen stations. Use only readings strictly before each target date when building neighbor inputs.
- Prohibition: do not use these holdout results to choose features, tune hyperparameters, revise the neighbor rule, or select a model. Any such changes require a new version and a new future holdout.
- Status: pre-registered; evaluation not run. The user-provided project handoff identified these 2024 January and May rows as remaining untouched holdout data.

## 2026-10-31: Neighbor parity tails and mismatch-only leakage diagnostic

- Scope was limited to target and source observations through 2023. The pre-registered 2024 January/May holdout rows were excluded from this diagnostic and were not scored.
- Across 91,683 modeling rows through 2023, 87,211 rows had both stored and reconstructed mean/distance values. Absolute mean difference: median 0.0 m, p90 0.0 m, p99 2.60 m, max 31.943 m. Missingness pattern agreement was 99.846%.
- Absolute distance difference for the reconstructed contributing-neighbor distance: median 0.02354 km, p90 0.12247 km, p99 0.24919 km, max 0.61791 km (87,211 common finite rows; missingness pattern agreement 99.846%).
- Stored count agreed on 97.836% of modeling rows; 1,984 rows had a different count.
- On those 1,984 count-mismatch rows only, nearest_time_any was tested with the reconstructed candidate selection (K=5, 40 km, nearest-first). It matched the stored mean in 1 row and all three stored values in 1 row; neither match used a later reading. The mode did select at least one later reading in 1,520 rows, but those values did not reproduce the stored mean. This finds no leakage signal for that tested candidate, but does not prove the unrecovered historical generator was leakage-free.
- Distance-definition diagnostic on positive-count rows: stored distance was closer to the reconstructed contributing-neighbor distance (median absolute difference 0.02354 km, p99 0.24919 km, max 0.61791 km; 34.01% within 0.01 km) than to the static nearest-station distance (median 0.03910 km, p99 15.60872 km, max 34.92969 km; 27.42% within 0.01 km). This does not identify the historical distance rule.
- The earlier 47.1% `all3` score is the fraction of a 1,200-row random sample where mean, count, and distance all matched simultaneously (distance could match either dynamic or static definition). The 97.8% figure is count-only agreement over all modeling rows. They use different match criteria and denominators and are not contradictory.
- Calendar encoding confirmed in `scripts/build_dataset.py`: `month_sin = sin(2*pi*MONTH/12)` and `month_cos = cos(2*pi*MONTH/12)`, where MONTH is 1 through 12.
- Detailed values: `docs/results/neighbor_mismatch_audit.json`.

## 2026-11-01: Request-time month-start cutoff sensitivity

- Question: offline reconstructed features use the exact observation date as the strict-prior cutoff, while the backend receives only month/year and uses the first day of the target month. The two cutoffs are therefore not identical.
- Diagnostic: `scripts/check_month_start_cutoff.py`, deterministic 3,000-row sample from 2005–2023; source observations capped at 2023-12-31, excluding the preregistered 2024 Jan/May holdout.
- Neighbor-input results: count differed on 0.4% of rows; request-time count became zero where exact-date count was positive on 0.0%; mean differed by >0.01 m on 6.7% of rows with values on both sides (absolute difference median 0.000 m, p90 0.000 m, p99 2.287 m, max 9.978 m); distance difference median/p90 0.000 km, max 4.733 km.
- Paired frozen-v2 prediction sensitivity: `scripts/check_month_start_prediction_impact.py`, same 3,000 rows and same 2023-12-31 source cap. Absolute prediction delta median 0.000 m, p90 0.000 m, p95 0.064 m, p99 1.203 m, max 10.627 m; 0.4% of rows changed by >3.7 m; mean signed month-start minus exact-date change +0.003 m.
- Interpretation: the cutoff changes some feature values and rarely changes predictions materially; this is a sensitivity analysis, not an accuracy evaluation or proof of the historical generator. Keep the operational month-start cutoff and frozen v2; no retraining or rule change is indicated by this diagnostic. The 2024 Jan/May holdout remains untouched.
- 2026-11-01 local verification: backend test suite passed (9 passed, 2 dependency deprecation warnings). Temporary API smoke with a disposable SQLite copy returned health `ok`, model v2 loaded, Nareli/Ajmer search returned one match, and July 2023 prediction returned 18.83 m with five neighbors. Temporary Streamlit server returned HTTP 200. Temporary servers and database copies were stopped/removed; the project database and frozen model were not modified.

## 2026-11-02: Pre-registered 2024 Jan/May holdout scored once

- The pre-registered 742 rows (668 January, 74 May) were scored once with the frozen v2 artifact; no model fit, feature selection, hyperparameter tuning, or neighbor-rule change was made from the result.
- Inputs used reconstructed v3 neighbors: exclude target `SITE_ID`; five nearest other stations within inclusive 40 km, selected before checking reading availability; latest source reading strictly before each target date; source observations capped at 2023-12-31. No target row had zero contributing neighbors; mean contributing count was 4.985.
- Combined holdout: MAE 4.050 m, RMSE 7.121 m, R2 0.9020 (n=742). January: MAE 3.870 m, RMSE 6.998 m, R2 0.8791 (n=668). May: MAE 5.667 m, RMSE 8.143 m, R2 0.9400 (n=74).
- All 742 target stations were already in train/validation station IDs; unseen-station subgroup n=0, so no unseen-station holdout metric exists. These are 2024 known-station temporal results, not new-location accuracy and not directly comparable to the 2022-2023 score without noting the different sample and inputs.
- Reproducible evaluator: `scripts/evaluate_holdout_2024.py`; saved result: `docs/results/holdout_2024_jan_may_v3.json`. The script does not modify the database/model. Keep the holdout closed for future tuning; any model/rule change needs a new later holdout.

## 2026-11-02: v3 interval candidate (not deployed)

- Built a separate candidate from train-only (`SPLIT=train`, 2005-2020) GroupKFold(5) OOF predictions using reconstructed v3 features; 50,363 rows / 1,403 stations, frozen RF settings, scikit-learn 1.9.0. The 2024 holdout was not read by this procedure.
- Candidate residual table uses five predicted-level bins and 10th/90th residual quantiles. Its cross-fit coverage diagnostic was 79.91% pooled; fold values 79.53%, 81.55%, 80.02%, 78.93%, 79.50%. Mean fold widths were 24.10, 23.57, 23.38, 23.42, and 25.19 m.
- The candidate is saved at `docs/results/interval_v3_candidate.json`, generated by `scripts/build_v3_interval_candidate.py`. It remains **candidate only**: the live `models/v2/interval_table.json` and backend warning were not changed during the Demo 2 run. The cross-fit diagnostic is not an independent external coverage guarantee.
- Review the candidate after the demo, confirm the calibration protocol and run regression checks before replacing the serving table. Do not use holdout rows to tune the table.
