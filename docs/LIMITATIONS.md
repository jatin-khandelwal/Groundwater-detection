
## Update (dataset_v2_1)

- Stage (`STAGE_EXTRACTION_PCT`, `CATEGORY_CODE`, district stage columns) 2023 ka ek hi snapshot hai (302 blocks). 2005-2023 ke har saal ke liye same value rehti hai, isliye ye time ka asar nahi dikhata, district ki pehchaan jaisa kaam karta hai. Ablation mein hamesha alag group.
- District stage 3 spelling fixes ke baad match hua: Chittorgarh/CHITTAURGARH, Dholpur/DHAULPUR, Jalore/JALOR. Over-exploited share `CATEGORY_CODE == "OE"` se (212 blocks); stage>100 se 216 aate hain.
- Station history features (`station_expanding_mean_m`, `level_same_round_prev_year_m`, `level_trend_lag1_lag2_m`, `station_prior_obs_count`) lag jaise hain: sirf Variant A.
- `level_same_round_prev_year_m` test mein 30.8% missing hai. NaN hi rakha, bhara nahi.
- `level_trend_lag1_lag2_m` mein -97 m se +102.8 m tak ke jump hain, shayad data errors. Saaf nahi kiye.
- Purana `rainfall_normal_mm` ka source verify nahi hua, isliye `unverified_do_not_use` mein. Uski jagah `rainfall_normal_train_mm` (2005-2020 se) use karo.
- Rainfall features (last monsoon, 6m/12m cumulative, anomaly) ke normals sirf 2005-2020 se. 2003 se pehle ki rows mein NaN (rainfall data 2004 se), wo model window ke bahar hain.
- AQUIFER_TYPE aur WELL_TYPE ki missing aur "Not Available" ko "Unknown" category banaya.

## Request-time neighbor cutoff and prediction sensitivity (2026-11-01)

- Training reconstruction uses readings strictly before each row's exact observation date; live requests use readings strictly before the first day of the requested month. This is a small but real input-definition difference because the interface accepts month/year, not a target day.
- On a deterministic 3,000-row 2005–2023 sample (all source observations capped at 2023-12-31), neighbor count differed on 0.4% of rows; neighbor mean differed by more than 0.01 m on 6.7% of rows with values under both cutoffs. Mean absolute difference was 0.000 m at median and p90, 2.287 m at p99, and 9.978 m at maximum.
- Feeding both input versions through the unchanged frozen v2 model gave absolute prediction changes of 0.000 m at median/p90, 1.203 m at p99, and 10.627 m at maximum. Only 0.4% of sample rows changed by more than 3.7 m. This is paired prediction sensitivity, not an accuracy or holdout evaluation.
- The original historical neighbor generator remains unidentified, and the stored-feature count mismatches remain unresolved. Do not claim the reconstruction proves the original generator was leakage-free. The 2024 Jan/May holdout (742 rows) was scored once on 2026-11-02 under the preregistered protocol: MAE 4.050 m, RMSE 7.121 m, R2 0.902. It was not used for tuning; do not reuse it for model selection.

