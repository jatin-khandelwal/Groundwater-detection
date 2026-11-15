# Groundwater Intelligence Project Complete Learning Guide

## Is guide ka maqsad

Ye guide project ko bilkul shuru se samjhati hai: groundwater problem kya hai, data kaise aaya aur saaf hua, model kaise chuna gaya, API aur Streamlit app prediction kaise banate hain, team roles kya hain, aur viva mein kaun se sawal aa sakte hain. Iska focus tumhe project samjhana hai, sirf ek speech ya memorized answers dena nahi. Har jagah verified project facts aur unresolved limitations ko alag rakha gaya hai.

## 1. Project ko ek minute mein samjho

Humne Rajasthan ke historical groundwater monitoring data se seasonal **depth-to-water** estimate banaya hai. User koi place search karta hai, app us jagah ke coordinates leta hai, backend aas-paas ke monitoring stations ki purani readings se model inputs banata hai, phir frozen Random Forest v2 prediction deta hai. Saath mein model range, relative depth band, confidence label, nearby observed readings aur alag historical borewell-depth advisory dikhata hai.

Prediction ka target `WLS_WTR_LEVEL` hai, metres mein **zameen se paani tak ki gehrai**. 20 m ka matlab paani satah se 20 metre neeche; number bada ho to paani aur gehra hai. Ye borewell ki total drilling depth nahi hai. Prediction seasonal/area estimate hai; searched ghar, khet ya college par sensor measurement nahi.

## 2. System ka end-to-end naksha

```text
CGWB / India Data Portal water-level records     NASA POWER climate records
                   |                                      |
                   +--> Role 1: clean, match, join, QC, features
                                      |
                         dataset_v2_3.csv + split metadata
                                      |
                         Role 2: experiments and validation
                                      |
                   frozen Random Forest v2 + metadata JSON
                                      |
User place --> Streamlit UI --> FastAPI --> SQLite station/readings lookup
                                      |        |
                                      |        +--> nearest stations, prior readings,
                                      |             model feature vector
                                      +--> prediction + context/warnings
                                      |
                                  UI result
```

Pipeline ke do alag hisse samjho. **Offline/modeling pipeline** bahut saari rows par dataset aur model banata hai. **Live/demo pipeline** ek user request ko process karta hai; wo model dobara train nahi karta. API frozen model load karke sirf `predict()` karta hai.

## 3. Groundwater terms jo bolne se pehle clear hone chahiye

| Term | Is project mein matlab |
|---|---|
| Water level / depth-to-water | Ground surface se groundwater tak vertical distance, metres mein. Bada number = paani zyada neeche. |
| Borewell `WELL_DEPTH` | Borewell/dug well ki banayi gayi total gehrai. Ye water level se alag variable hai. |
| Monitoring station | Ek fixed CGWB ya linked station jahan alag dates par water level record hota hai. |
| Observation round | Aam seasonal reading window: January, May, August, November. Har station har round mein zaroor nahi aata. |
| Feature | Model ko diya input, jaise coordinates ya nearby prior level. |
| Target | Model ka jawab jise predict karna hai: `WLS_WTR_LEVEL`. |
| Leakage | Training mein aisi information ghus jana jo prediction time par available nahi hoti, jaise target row ka current/baad ka level. Isse score jhootha achha ho sakta hai. |
| Holdout/test | Data jise decisions/tuning ke liye use nahi karna; final evaluation ke liye alag rakha jata hai. |

`WELL_DEPTH` ko target samajhne ki galti na karo. Hum user ke liye groundwater depth-to-water estimate karte hain; advisory endpoint alag se historical well-depth records ka p75 reference deta hai.

## 4. Data: kahan se aaya aur kya bana

### 4.1 Water-level sources aur station matching

Project pipeline mein state/district CGWB table aur India Data Portal/CGWB-linked manual table ko standard columns mein badla jata hai. Station codes har source mein barabar nahi the, isliye `scripts/build_waterlevel.py` geographic matching karta hai: latitude/longitude par Haversine/BallTree distance, 1 km tak candidate match, aur ek state-source station se multiple candidates judne par sabse paas wala record. Matched station ko source station code milta hai; match na mile to coordinate-aadharit synthetic ID `A_<lat>_<lon>` banta hai. Unmatched station list bhi output hoti hai, taaki matching ko chupke se assume na kiya jaye.

Same station + same calendar month mein sources overlap karen to script difference inspect karti hai; final deduplication mein source A ko priority di gayi hai. Is choice ka reason ek predictable single row per station-month dena hai, lekin source preference/documentation phir bhi zaroori hai. `SITE_ID + DATE` duplicates ko dataset builder silently delete nahi karta; duplicate mile to rukta hai.

Key fields: `SITE_ID`, `DATE`, `LAT`, `LON`, `DISTRICT_NAME`, `STATION_NAME`, `WLS_WTR_LEVEL`, `WELL_DEPTH`, `WELL_TYPE`, `AQUIFER_TYPE`, `SOURCE_DS`, `ROUND`. `SOURCE_DS` traceability ke liye hai, deployed feature nahi.

### 4.2 Rainfall aur climate joins

Rainfall/climate records 0.5-degree grid cells par hain, station coordinates par nahi. `build_dataset.py` station coordinate ko nearest rounded half-degree grid key deta hai, phir grid + year + month se climate data jodta hai. Ye ek approximation hai: aas-paas ki grid cell ka monthly value, station ke exact point ka rain gauge measurement nahi.

Dataset v2.1/v2.2/v2.3 banate waqt pehle ke mahino ke rainfall, temperature/humidity, PET, soil wetness, evaporation aur anomalies jaise extra candidate features banaye gaye. Rolling features mein `shift(1)`/previous months ka use current month ko hataane ke liye hota hai. Normal/anomaly reference 2005-2020 training years se banta hai. NASA POWER missing fill values ko missing maana jata hai, aur monthly aggregation ke liye valid-day threshold hota hai. Ye saare candidate features final model mein nahi gaye; data banana aur model mein rakhna ek hi faisla nahi hai.

### 4.3 Row aur dataset versions

Project record ke mutabik `dataset_v2_3.csv` mein 92,452 rows aur 77 columns hain; modeling window 2005-2023 hai. Earlier handoff versions (v2_1, v2_2) intermediate checkpoints hain. Final model metadata `models/v2/metrics.json` mein `dataset_v2_3.csv` likhta hai. Live SQLite tables current model ke liye alag, query-friendly representation hain. Isliye CSV aur SQLite dono ko ek hi file ya same purpose mat samjho.

### 4.4 Quality checks: galti ko flag karna, chhupana nahi

`scripts/qc_flags.py` separate flags banata hai: level 0-300 m range ke bahar, adjacent-history jump 50 m se bada, ya recorded well depth se level deeper. Row delete karne ke bajay `QC_*`/`QC_ANY` flag ki jati hai. Isse suspicious data visible rehta hai aur evaluation mein with/without-QC comparison mumkin hota hai. Flag ka matlab source observation galat sabit hona nahi; manual/domain review ki zarurat ho sakti hai.

`finalize_role1.py` dates, duplicate keys, target missingness, Rajasthan coordinate bounds, rainfall missingness, lag order, neighbor consistency, elevation range aur year-round counts check karta hai; phir split, feature groups, dictionary, handoff aur limitations files banata hai. Script ke comments uske expected inputs/outputs batate hain; run karne se pehle dataset version aur paths check karne chahiye.

## 5. Role 1: Data ka kaam - detail se

Role 1 ka objective hai raw sources ko reproducible, traceable aur modeling ke laayak banana. Model achha ho ya bura, wo input table aur target definition par depend karta hai; isi liye cleaning/joins ko model code se alag rakha gaya.

### Role 1 ka kaam step by step

1. **Source files pehchanna:** water-level file, station master/block map, rainfall/climate series, elevation aur stage tables. Har source ka unit, date range, station key aur missingness samjho.
2. **Headers/types standardize karna:** date ko date, coordinates/levels ko numeric, IDs ko string. ID ko float bana dene se leading zeros ya `.0` issue aa sakta hai; isliye `SITE_ID` string rakha jata hai.
3. **Rajasthan scope aur station identity:** relevant state/coordinates filter karna; station records ko coordinates se link karna; match radius aur unmatched list preserve karna.
4. **Repeated records resolve karna:** source overlap aur station-month duplicate inspect karna; chosen source priority document karna. Same station-date duplicate ko silently drop nahi karna.
5. **Metadata join:** station se district/block/elevation/well metadata; spatial climate grid se monthly rainfall/climate. Merge validate karna ki rows bina wajah multiply na hon.
6. **Derived values:** date/year/month/round, cyclic month sin/cos, historical lags, rolling summaries, climate lag/anomaly, neighbor values. Har feature ke liye poochho: prediction date par kya ye available hota?
7. **QC:** missingness, value range, duplicate key, coordinates, temporal order, impossible/suspicious pairs, row-count invariants aur source-vs-joined counts.
8. **Splits aur lineage:** 2005-2020 train, 2021 validation, 2022-2023 test; unused periods ko train/test mein galti se na ghusao. Data dictionary aur group JSON se har column ka meaning/purpose likho.
9. **Handoff:** model role ko versioned dataset + feature groups + dictionary + limitations; backend ko station/readings/climate tables; frontend ko sample data/metrics and truthful labels.

### Role 1 ke decisions kyun aise hain

- **Source A/B ko coordinates se link:** names spelling ke kaaran unstable hain, geographic key practical hai. 1 km threshold false matches ko limit karta hai, par threshold ke paas ke matches manually audit hone chahiye.
- **IDs strings:** identifiers categories/keys hain, measured quantity nahi. Numeric coercion ID ko distort kar sakti hai.
- **One row per station-time key:** repeated readings merge/evaluation mein double-counting na karen. Dedupe rule explicit hona chahiye, automatic data loss nahi.
- **0.5-degree grid join:** climate gridded hai; nearest cell available, exact station weather nahi. Is uncertainty ko limitation mein kehna.
- **QC flag, delete nahi:** reviewer original row dekh sakta hai; QC sensitivity compare ho sakti hai. Sirf flag se row hata dena selection bias bana sakta hai.
- **Split ko timestamp se define:** future data ko past training mein mix nahi karte; random row split station history ko train aur test dono taraf rakh sakta hai.
- **Target-adjacent same-station history ko candidate rakha, par freeze model mein nahi:** new borewell/location par apne station ki prior readings ho hi nahi sakti. Is use case mein unavailable lag par model depend karna unsafe hai.

### Role 1 ko viva mein dikhane layak files

- `scripts/build_waterlevel.py`: source A/B normalize, spatial matching, overlap, dedup, master outputs.
- `scripts/build_dataset.py`: base data, monthly rain grid joins, lagged rainfall/history, month encoding.
- `scripts/add_climate_features.py`, `scripts/add_climate2_features.py`: climate feature versions, previous-month logic.
- `scripts/qc_flags.py`: suspicious-row flags.
- `scripts/finalize_role1.py`: final checks, splits, groups, handoff outputs.
- `data/processed/data_dictionary_v2.csv` aur `data_dictionary_v2_1.csv`: column meaning, version mismatch samajhne ke liye.

Note: current root README kuch jagah purana/galat folder description deta hai. Current API `dataset_v2_3` metadata use karta hai aur actual UI `frontend/streamlit_app.py` Streamlit app hai; README mein React + Leaflet likha hai. Viva/doc ko actual code ke hisaab se bolo, purane README ke hisaab se nahi.

## 6. Role 2: Model banana aur evaluate karna

Role 2 ka objective hai aisa model select karna jo intended use ke liye generalize kare, inference par ban sakne wale inputs use kare aur leakage se bach sake. “Sab features daal do” model development nahi hai. Candidate feature group ko score, future availability, meaning, missingness aur backend implementability par judge kiya gaya.

### 6.1 Problem formulation

- **Regression:** jawab continuous metres mein; classification nahi.
- **Target:** `WLS_WTR_LEVEL`.
- **Unit/direction:** m depth-to-water; larger = deeper groundwater.
- **Prediction time:** requested location aur month/year. Is waqt `WELL_DEPTH` ya target reading nahi pata honi chahiye.
- **Intent:** seasonal location estimate. Daily forecast, exact property measurement ya safe drilling depth guarantee nahi.

### 6.2 Train/validation/test ka reason

Final temporal protocol: 2005-2020 train, 2021 validation, 2022-2023 test. Validation par decisions/hyperparameters ki ja sakti hain; model freeze ke baad test ek hi baar report hota hai. Test stations training mein dekhe gaye the, isliye ye future time par **known stations** performance hai, unfamiliar-location performance nahi.

Naye station ki performance alag naapne ke liye train par `GroupKFold(5)` ko `SITE_ID` ke groups par chalaya. Har fold mein poora station ya to train side mein hota hai ya validation side mein. Isliye station ke apne past/future observations do taraf bantkar leakage jaisa asar nahi dete. New district ke liye leave-one-district-out evaluation district generalization ka tougher check hai.

2024 ke Jan/May ki 742 rows (668 Jan + 74 May) preregistered holdout ko 2 Nov 2026 ko frozen v2 aur reconstructed v3 neighbor inputs ke saath protocol ke anusaar ek baar score kiya: MAE 4.050 m, RMSE 7.121 m, R² 0.9020. Saare 742 stations training/validation mein pehle se the; unseen-station subset khaali tha. Is result se model tune nahi hua. Ab is holdout ko future tuning ke liye dobara use mat karo.

### 6.3 Metrics ka seedha matlab

| Metric | Asaan matlab | Unit / achha kis taraf |
|---|---|---|
| MAE | Har row par absolute metre error ka average | metres; kam achha |
| MedAE | Absolute error ka beech wala (median) value | metres; kam achha; bahut bade outliers se MAE se kam prabhavit |
| R2 | Baseline mean ke mukable model kitni variation explain karta hai | unitless; 1 perfect, 0 mean baseline ke barabar, negative usse bhi kharab ho sakta |
| RMSE | Error ka square-average, phir square root | metres; bade errors ko MAE se zyada weight |
| CV | Training data ke folds par repeat evaluation | har fold ke test jaisa unseen part ka score, ek final holdout nahi |

MAE 7.531 m ka matlab 7.531% accurate nahi. Iska matlab unseen-station CV mein absolute error average lagbhag 7.5 m tha. R2 0.69 ka matlab “69% accuracy” bhi nahi.

### 6.4 Baselines aur model comparison

Pehle simple reference chahiye: training mean aur persistence (pichhli same-station reading ko next estimate) jaise baselines. Baseline batata hai ML model ne sach mein value add ki ya nahi. Persistence existing-station time test mein strong ho sakta hai, par new station ke liye us station ka lag missing hota hai; isliye same rows par fair comparison zaroori hai.

Experiments mein Random Forest aur XGBoost, feature groups, hyperparameters, lag-available/no-lag variants, QC sensitivity aur CV checks aaye. Tabular nonlinear problem ke liye Random Forest practical tha: trees nonlinear boundaries/interactions seekh sakte hain, scaling ki zarurat nahi, mixed categories pipeline ke zariye handle hote hain. Par RF har use ke liye “best algorithm” nahi; yahan frozen chosen model ka reproducible evidence relevant hai.

Grouped permutation-importance output mein neighbor group ko shuffle karne par MAE lagbhag 5.315 m badha. Iska matlab is evaluation setup mein model neighbor inputs par kaafi nirbhar tha. Ye causal proof nahi: correlated features, sample/split aur shuffle method importance ko prabhavit karte hain.

Model preprocessing pipeline training fold ke andar fit hota hai: numeric missing values median + missing indicator; categorical missing `Unknown`, one-hot encoding; unseen categories ignore. Isse validation fold ka distribution preprocessors mein leak nahi hota.

### 6.5 Feature ablation: feature kyun rakha ya nikala

Decision record mein predeclared rule tha: group ko deployed model mein tabhi rakho jab new-station CV mein R2 gain kam-se-kam 0.01 ho aur backend inference par woh feature bana sakta ho. Test score ko feature chunne ke liye use nahi karna.

| Feature group | Decision | Reason |
|---|---|---|
| District, latitude, longitude, year, sin/cos month | Rakha | Location/time ka basic signal, request se available. |
| Elevation | Rakha | Naye point ke liye station/elevation mapping se estimate hota; ablation gain ~0.069. |
| Neighbor prior level, nearest contributing distance, count | Rakha | Strong spatial context; ablation gain ~0.044; live database se reconstruct kiya ja sakta. Ye sabse sensitive operational dependency hai. |
| Rainfall | Final input nahi | New-station CV gain ~0.005; current rainfall future request par known na bhi ho. Dashboard selector prediction ko badal nahi sakta. |
| Well/aquifer type | Final input nahi | Gain ~0.007; new borewell ka type/total depth advance mein pata nahi; type target context ka proxy ban sakta. |
| Extraction stage | Final input nahi | Snapshot/coverage/missingness concerns; improvement small ya negative, year-wise real value nahi. |
| Extra climate/PET/soil | Final input nahi | Gain threshold pass nahi hua; live availability/forecast assumptions extra complexity. |
| Same-station lag features | Final model nahi | New locations/stations par unavailable; intended location-search workflow se mismatch. |

`WELL_DEPTH`, `LEVEL_DIFF`, current target aur QC/outlier bookkeeping columns forbidden/input nahi hain. `WELL_DEPTH` leakage-like shortcut ban sakta hai: well geometry khud water level distribution se judi ho sakti hai aur new borewell par maloom nahi hoti.

### 6.6 Final frozen model

Model `RandomForestRegressor` hai; metadata mein 100 trees, max depth 20, max_features 0.4, minimum leaf 1, random seed 42. Final artifact training + validation years (2005-2021) par fit hua; 2022-2023 test alag rakha gaya. Exact input contract `models/v2/feature_list.json` mein hai:

1. `DISTRICT_NAME` - mapped administrative label/category.
2. `LAT`, `LON` - selected place coordinates.
3. `YEAR` - request year; model future trend ko reliably extrapolate nahi karta.
4. `month_sin`, `month_cos` - `sin(2*pi*month/12)`, `cos(2*pi*month/12)`; January aur December seasonal circle par paas rakhe jaate hain.
5. `elevation_m` - nearby/available station elevation estimate.
6. `neighbor_prev_level_mean_5_m` - eligible contributing neighbors ke prior level ka mean.
7. `nearest_neighbor_prev_distance_km` - contributing neighboron mein sabse paas ki distance.
8. `neighbor_prev_level_count_5` - 0-5 contributing station count.

Month ko sirf 1 se 12 integer dene par tree model December aur January ko far apart samajh sakta. Sine/cosine periodic encoding seasonal continuity ko represent karta hai.

## 7. Neighbor feature: sensitive rule aur bachi hui uncertainty

Original historical script jo purane stored neighbor columns banati thi, recover nahi hui. Neeche ka rule current approved operational reconstruction hai; ise “original generator ka proven exact rule” nahi kehna.

1. Target ki apni `SITE_ID` available ho to us station ko exclude karo.
2. Target coordinates se Haversine distance nikalo.
3. 40 km **inclusive** ke andar ke up to 5 nearest other stations pehle select karo.
4. Availability check ke baad 6th station se replacement nahi hota.
5. Har selected station ki target cutoff se strictly pehle latest reading lo; maximum age limit nahi.
6. Jis selected station ki prior reading na ho use skip karo.
7. Available levels ka average, available station count, contributing stationon mein shortest distance banao.
8. Count 0 ho to mean aur distance missing/NaN; count 0. Distance/mean ko fake zero mat do.

**Leakage assurance ki boundary:** `build_neighbor_v3.py` ne rebuilt rows ke source dates target date se strictly pehle assert kiye. Ye rebuilt data timing test hai. Ye historical original generator ko recover nahi karta aur uske leakage-free hone ka proof nahi. 2.2% count mismatch ka historical cause unresolved hai.

**Training/live cutoff difference:** Offline reconstruction exact observation date se pehle dekhti hai. Live interface sirf month/year leta hai aur month ke first day se pehle readings leta hai. 3,000 rows ke deterministic 2005-2023 sample par count 0.4% rows mein alag, mean 6.7% cases mein >0.01 m alag; mean difference p99 2.287 m, max 9.978 m. Frozen model ko dono inputs dene par prediction delta median/p90 0, p99 1.203 m, max 10.627 m; 0.4% rows mein delta >3.7 m. Ye sensitivity analysis hai, accuracy test nahi. Is result par model retrain nahi hua.

Reconstructed v3 features par train-only new-station CV: R2 0.6941, MAE 7.501 m, compared with stored-input 0.6902 and 7.531 m. Predeclared tolerance gate pass hua; frozen v2 ko retain kiya. 2022-2023 test dobara tune nahi hua. V3 interval ka train-only candidate banaya (79.91% cross-fit coverage diagnostic), lekin live saved interval table abhi purane stored inputs wali hai; candidate ko review ke bina activate nahi kiya.

## 8. Backend: request se prediction tak

Backend FastAPI API hai. Startup par DB path check/optional initialization, additive runtime schema, model artifact load hota hai. Model load fail ho to health degraded aur `/predict` unavailable; dummy model silently use nahi hota. Ye fail-closed design galat confidence ke saath answer dene se behtar hai.

### `/predict` ka flow

1. Pydantic `PredictRequest` input validate karta: month 1-12, year 2005-2100, lat/lon Rajasthan bounds mein aur dono saath, location fields consistent.
2. `FeatureService.resolve_target()` choose karta: existing `site_id`, explicit searched coordinates plus district, ya district/block station-centroid fallback.
3. For searched place: app selected Nominatim result ke lat/lon pass karti; prediction wahi coordinates use karti. District sirf canonical category/context hai.
4. Backend sab mapped station coordinates se target distance compare karta; target site exclude if known; up to five within 40 km sort karta.
5. Har selected station ke liye SQL latest level `date < first day of requested month` leta.
6. Mean/distance/count, season cycle, year, location and elevation mila kar exact ten-column feature mapping banata.
7. `ModelService.predict()` verifies exact required feature names and preserves feature order, then frozen pipeline `.predict()` calls.
8. Saved residual interval, risk band, confidence/warnings and nearby station details add hote hain; request/response SQLite log mein save hota hai.

Important code: `backend/app/services/feature_service.py` location resolution + features; `model_service.py` model load/predict/interval; `routers/predict.py` API orchestration; `schemas.py` request validation; `db.py` import/schema; `main.py` startup and routers.

### API endpoints ka purpose

| Route | Use |
|---|---|
| `GET /health` | Backend, DB, model loaded state. |
| `GET /districts`, `/blocks` | Select/dropdown metadata. |
| `GET /locations/search?q=...` | User place name to Rajasthan coordinates, via public Nominatim; internet needed for uncached searches. |
| `GET /stations` | Map markers/latest observations, default as-of date 2023-12-31. |
| `GET /history` | Station/block water-level history and nearest rainfall-grid time series. |
| `POST /predict` | Frozen model estimate, input echo, interval, neighbor explanation and warnings. |
| `POST /advisory` | Historical well-depth distribution, stage status, provisional reference. |
| `GET /model/info` | Feature list and validation context. |

### Location search aur uncertainty

Place names geocoder ko query kiye jaate hain; results Rajasthan bounds mein filter aur SQLite mein 90 din cached. Requests ~1 second se zyada interval par throttle. Nominatim attribution UI mein dikhana zaroori. Internet fail ho to cached results hi mil sakte hain. Search result ka displayed address observation station address nahi hai.

### Data persistence

`backend/data/groundwater.sqlite3` read-oriented station/readings/rainfall/stage data aur runtime cache/log tables rakhti hai. Relational DB select/query/time filtering ke liye; model pickle learned estimator hai. SQLite DB ko har request mein raw CSV padhne se bachne ke liye use karte hain. `GW_AUTO_INIT_DB=0` startup import rokta; `GW_DATABASE_PATH`, `GW_MODEL_PATH` paths configure karte hain.

## 9. Model ke numbers aur unka honest use

| Test ka sawal | Metric | Sahi interpretation |
|---|---|---|
| Naya station? GroupKFold(5), SITE_ID grouped | R2 0.6902, MAE 7.531 m, MedAE 4.547 m | Location/station generalization ka relevant CV estimate. |
| Naya district? leave-one-district-out | R2 0.5868, MAE 9.037 m, MedAE 5.877 m | Naya district tougher; error zyada. |
| Future 2021, old stations | R2 0.9724, MAE 2.502 m | Temporal validation, seen stations. |
| Historical temporal test 2022-2023 | R2 0.9411, MAE 3.205 m, MedAE 2.067 m | 5,178 rows, all 934 test stations seen during training. Not new-location accuracy. |
| Persistence baseline on temporal test | R2 0.9403, MAE 2.648 m | Lower MAE on this seen-station test; unavailable for a new location with no station history. |
| Rebuilt neighbor v3 new-station CV | R2 0.6941, MAE 7.501 m | Train-only equivalence gate; not 2024 holdout. |

Score ka use hamesha “kaunsa population, kaun se years, kaun sa split, kaunsi feature definition?” ke saath karo. Temporal test ka high score kyunki station history train/test mein common hai. Naye address par CV ka ~7.5 m MAE zyada relevant hai.

## 10. Range, risk, confidence aur advisory ek cheez nahi

- **Prediction:** model ka central estimate metres mein.
- **Model range:** saved calibration ke residual quantiles se lower/upper; displayed width se confidence label. Current range old stored neighbor inputs se calibrate hai, reconstructed neighbor_v3 request inputs se nahi. Isse guaranteed “80% chance” mat bolo.
- **Relative depth band/risk:** thresholds 8 m aur 22 m hain; target-level distribution ke bands. “Higher” ka matlab model-defined deeper depth-to-water class, drilling failure/prohibition nahi.
- **Confidence:** interval width `<15 m` high, `15-30 m` medium, `>30 m` low; no neighbors to low. Ye statistical confidence ka universal calibrated probability nahi.
- **Borewell advisory:** historical `WELL_DEPTH` records ka p75; small block sample par district fallback. Default mein supervisor-approved buffer configured nahi. Historical depth distribution engineering/geotechnical/drilling safety guarantee nahi.

Saved interval method train par GroupKFold out-of-fold predictions se residuals banata hai: predicted level ke 20/40/60/80 percentile cut points se 5 bins, phir har bin mein residual ka 10th/90th percentile. Cross-fitted train coverage ~79.8% rahi. Purane 2022-2023 temporal inputs par coverage 94.3% aur mean width 22.53 m thi, lekin ye seen stations aur purane stored neighbor inputs ka result hai; v3 request path par is coverage ko validated mat bolo.

In concepts ko ek number mein collapse mat karo: predicted water level 18 m hone ka matlab recommended borewell drilling depth 18 m automatically nahi hota.

## 11. Frontend: user kya karta hai

Actual code `frontend/streamlit_app.py` hai (README ka React statement stale). Sidebar mein API URL/status aur sections: Overview, Stations, Prediction, Advisory, Trends, Model and data.

Prediction flow: user place text enter kare -> Find location -> matching geocoder result choose kare -> month/year choose kare -> Predict -> predicted metres/risk/confidence/range/warnings aur nearby station table dekhe. Nearby table useful transparency hai: station, distance, last reading date, level, model mein contributed flag. Ye user ko dikhata hai ki searched place par direct sensor reading nahi hai; model nearby station evidence se area estimate banata hai.

`st.cache_resource` HTTP client reuse karta, `st.cache_data` API reads ko TTL ke saath cache karta; forms multiple widget changes ko ek submit par batch karte; fragments map/prediction sections ko independent rerun karne mein madad karte. Isse repeated requests kam hote hain, lekin cold internet geocoding phir bhi delay ho sakti hai.

## 12. Demo setup aur walkthrough

PowerShell project root `C:\Ground water` mein:

```powershell
cd "C:\Ground water"
.\scripts\start_demo.ps1
```

Open `http://127.0.0.1:8501`; backend API `http://127.0.0.1:8000/docs`. Guided example: Prediction -> `Nareli, Ajmer` search -> matching place -> July 2023 -> predict. Verified local smoke example result: 18.83 m, five contributing neighbors, medium confidence. Ye demo output hai, Nareli ka independent measured truth nahi. UI warning karegi ki interval calibration neighbor_v3 ke liye update nahi hui.

Map par stations, prediction page par location/neighbors, trends par historical level/rainfall, model page par validation and limitations dikhao. 2022-2023 metric ko known-station temporal test aur 7.531 m CV ko new-station score ke label ke saath bolo. Place search live service par depend kar sakti hai; backup screenshot/video ready rakho.

Server band karne ke liye separate PowerShell:

```powershell
cd "C:\Ground water"
.\scripts\stop_demo.ps1
```

## 13. Viva mein common “humne aisa kyun kiya?”

**Random split kyun nahi?** Same station repeated measurements karta hai. Random split station identity/history ko dono sets mein baant kar overly optimistic result de sakta. Isliye time split aur SITE_ID grouped CV alag questions answer karte hain.

**Ek temporal test aur GroupKFold dono kyun?** Temporal test future dates par seen stations ka performance poochta hai. GroupKFold new/unseen station ka performance poochta hai. Deployment unfamiliar location maang sakta hai, isliye dono report karne chahiye.

**Rainfall kyun hata di jab groundwater par asar hai?** Domain relation hona kaafi nahi; feature live time par available hona, incremental validation value dena, clean lag rule hona aur backend se reproducibly milna chahiye. Is experiment mein candidate rainfall gain threshold se kam tha. Rainfall historical trends page par phir bhi useful hai.

**WELL_DEPTH kyun nahi?** User naya borewell plan kar raha hai; depth pehle se known nahi. Plus target context se sambandh ka shortcut ho sakta hai. Use karne se deployment mismatch/leakage risk.

**RF kyun?** Tabular nonlinear data, category preprocessing pipeline, simple deployable frozen artifact. Yeh evidence-based selected choice hai, har algorithm se universally superior claim nahi.

**Month sin/cos kyun?** Month cycle circular hai: December ke baad January aata hai; raw 12 and 1 numeric distance cycle ko represent nahi karta.

**40 km, 5 neighbors kyun?** Reconstructed historical rule audit aur neighbor-v3 CV gate ke operational rule mein ye values locked hain. Original generator recover nahi hua, so ise reconstructed approved rule bolna, exact historical source nahi.

**No max-age cutoff kyun?** Reconstruction rule mein nahi tha. Iska consequence stale reading ho sakti hai, isliye API warning dikhata. Age limit jodne se feature definition/model inputs badlenge; evidence/new version ke bina silently nahi badalna.

**Place name search mein district kyun bhejte hain?** Model ko categorical `DISTRICT_NAME` feature chahiye. Search coordinates point ko define karte hain; canonical district admin label hai. Neighbors target coordinates ke around nikale jaate hain.

**API, SQLite, Streamlit separate kyun?** UI presentation, API validation/business logic, database persistence/query aur model inference alag concerns hain. Isse model/UI ko separately change/test kar sakte hain.

**Advisory ko guarantee kyun nahi?** Historical `WELL_DEPTH` sample ka percentile geology, yield, casing, drilling safety, water quality ya permissions evaluate nahi karta; buffer supervisor-approved nahi.

## 14. Viva question bank with model answers

### Project aur groundwater

**Q1. Project kya karta hai?** Rajasthan location/month ke liye nearby historical observations aur frozen ML model se seasonal depth-to-water estimate deta hai; saath observed neighbor context aur provisional historical depth reference.

**Q2. Output kis unit mein hai?** Metres below ground / depth to water. Bada number ka matlab water table deeper below ground.

**Q3. Kya ye live sensor reading hai?** Nahi. Ye nearby stations aur model par based estimate hai; searched location par direct reading nahi.

**Q4. Water level aur borewell depth difference?** Water level ground se paani tak distance; WELL_DEPTH drilled structure ki total gehrai. Dono related ho sakte hain par interchangeable nahi.

**Q5. Kya app batata hai borewell safe ya successful hoga?** Nahi. Advisory historical depth percentile hai, guarantee nahi.

### Data aur Role 1

**Q6. Row kya represent karti hai?** Ek monitoring site ka ek dated water-level observation, station metadata aur joined/derived predictors ke saath.

**Q7. `SITE_ID + DATE` key kyun?** Ek site-date observation ko uniquely identify karne aur duplicates find karne ke liye.

**Q8. Station datasets ko kaise match kiya?** Coordinates par Haversine/BallTree nearest station search, 1 km threshold; unmatched entries alag report.

**Q9. Names se merge kyun nahi?** Spelling, aliases, punctuation aur inconsistent station naming se false non-match; coordinates extra evidence dete hain. Coordinate matching bhi perfect nahi, threshold audit zaroori.

**Q10. Climate value station-specific hai?** Nahi, nearest 0.5-degree grid-cell monthly estimate hai.

**Q11. Suspicious rows delete kyun nahi?** QC flag retain karta hai source observation and traceability; deletion se selection bias ho sakta hai. Flag factual verdict nahi.

**Q12. Role 1 ka primary deliverable kya?** Versioned modeling dataset, feature groups/dictionary, QC/split outputs, limitations, backend-readable source tables/handoff.

**Q13. 2005-2020 normals kyun?** Temporal validation/test ke future periods ko normal estimate mein leak hone se rokne ke liye train window se baseline banaya.

### Modeling aur Role 2

**Q14. Regression kyun?** Target continuous depth in metres hai, categories nahi.

**Q15. MAE 7.531 ka matlab?** New-station grouped CV mein average absolute error ~7.531 m; percentage accuracy nahi, aur guaranteed per-row error nahi.

**Q16. R2 0.6902 ka matlab?** CV prediction observed variability ko mean baseline ke mukable kitna explain karta hai; 69% rows correct nahi.

**Q17. 0.9411 score ko new-location performance kyun nahi bolte?** 2022-2023 test ke all 934 stations train mein bhi the; ye seen-station future years test hai.

**Q18. GroupKFold mein group `SITE_ID` kyun?** Same station ki rows train/validation mein split na hon, taaki unseen-station question realistic ho.

**Q19. District CV result kam kyun?** Naya district spatial/admin distribution shift; district-specific patterns train mein nahi dekhe. Ye expected tougher generalization test hai.

**Q20. Feature ablation kya?** Feature group add/remove karke same evaluation protocol par score difference dekhna, value vs complexity assess karna.

**Q21. Rainfall final feature kyun nahi?** Is run mein gain ~0.005 (<0.01 gate), request-time scenario/live future availability mismatch; so model input nahi. Historical plot possible.

**Q22. Well type kyun nahi?** Unknown/new borewell class deploy-time known nahi; type depth context proxy ho sakta; CV gain small.

**Q23. Missing values?** Pipeline numeric median + missing indicator; categorical Unknown + one-hot. Imputer training fold pe fit hota.

**Q24. Missing neighbor mean zero kyun nahi?** Zero actual 0 m reading jaisa meaning de sakta; missingness is distinct. Keep NaN plus count 0; model pipeline handles missing.

**Q25. Persistence baseline kya hai?** Last observed same-station value ko next reading prediction maana. Known station pe useful baseline, new station pe unavailable.

### Leakage, neighbor rule, holdout

**Q26. Leakage ki example?** Current target ya future observation ko lag/neighbor feature mein use karna.

**Q27. Strictly prior ka code idea?** Time-sorted station readings mein `searchsorted(cutoff, side="left") - 1`; left insertion point se cutoff se strictly earlier index milta.

**Q28. Kya historical neighbor leakage-free prove kiya?** Nahi. Reconstructed table timing assertion pass; tested one alternative future-reading candidate did not explain mismatches, but historical generator missing. “Prove” nahi kehna.

**Q29. 2024 holdout ka status?** 742 Jan/May rows ko 2 Nov 2026 ko preregistered protocol ke mutabik ek baar score kiya: MAE 4.050 m, RMSE 7.121 m, R² 0.9020. Saare stations known the; new-station result nahi. Is result par tune nahi kiya aur holdout ko dobara model selection ke liye use nahi karna.

**Q30. Cutoff sensitivity result accuracy hai?** Nahi, frozen model ko input variant A/B dene se paired prediction shift measure hai, labels se error calculate nahi hota.

**Q31. Max prediction delta 10.627 m ka kya?** Tail case shows rare large sensitivity; median/p90 zero, p99 1.203m. It's material to report, not hide; no retrain was triggered from this diagnostic.

### Backend/UI/deployment

**Q32. Model artifact kya hai?** Saved sklearn pipeline pickle + feature list/columns/metrics/interval JSON; API loads once and predicts without training.

**Q33. Pydantic kyun?** Request shape/ranges/paired-coordinate constraints validate before business logic; malformed input gets clear HTTP errors.

**Q34. Haversine kyun?** Earth surface par lat/lon points ki great-circle distance approximate km; Euclidean degrees distance se better.

**Q35. Nominatim ka role?** Text place ko coordinates/admin address se resolve karta; it doesn't supply groundwater measurement. Public service needs network, caching/throttle/attribution.

**Q36. SQLite kyun?** Demo-scale local relational data and indexed lookups, no separate DB service needed; multi-user production scaling is another concern.

**Q37. `health` green kya guarantee karta?** API can see loaded model and database. Ye prediction scientifically correct hone ki guarantee nahi.

**Q38. Confidence high ka matlab 95% probability?** Nahi. Width-based rule; calibrated probability claim nahi, especially v3 inputs par calibration mismatch.

**Q39. Why Streamlit?** Python-first fast demo UI and direct API calls; current project code uses Streamlit. README React mention stale.

**Q40. Agar Nominatim down?** Uncached searches fail; local API/database/model can still serve known coordinates or other UI options where available. Demo se pehle internet/backups check.

**Q41. Model ne persistence baseline ko beat kiya?** 2022-2023 seen-station test par model MAE 3.205 m tha, persistence MAE 2.648 m; is test par persistence ka average absolute error kam tha (R2 model 0.9411, persistence 0.9403). Lekin persistence ko naye station/place par pichhli same-station reading ke bina chalaya nahi ja sakta. Dono scores alag deployment sawal answer karte hain.

## 15. Role-wise team handoff and ownership

Actual individual ownership ko team ke kaam ke hisaab se confirm karna; repo files contributor identity prove nahi karte. Neeche role responsibility map hai.

### Role 1 - Data

Owns source inventory, schemas, merge/matching rules, units/IDs/dates, station/block metadata, climate grid joins, QC flags, leakage-safe derived data, split column, data dictionary, versioned exports, reproducibility and limitations. Must explain every row/column and why a join did not inflate row count. Demo evidence: data quality counts, duplicate/missing checks, station match threshold, split counts and dictionary.

### Role 2 - Modeling

Owns target/features, prohibited predictors, baseline, train/validation/test strategy, GroupKFold/leave-district-out, preprocessing pipeline, candidate algorithms, hyperparameters, ablation gate, residual interval method, frozen artifact/metrics and honest model card. Must explain why test was not repeatedly tuned and why high temporal score is not new-site accuracy.

### Backend role

Owns FastAPI routes/schemas/errors, DB initialization/import, request-time feature construction, model loading/inference, interval/risk response, geocoding/cache/throttle, history/advisory and tests. Must keep feature contract and neighbor logic consistent with model training reconstruction, and never return fabricated prediction if model missing.

### Frontend role

Owns Streamlit screens and API flow: connection state, overview, station map/table, place search, prediction and nearby evidence, advisory, trends, model/limitations. Must label units/splits and warnings, avoid claiming live measurement, ensure search result coordinates and selected place are carried into request.

### Team integration responsibility

Shared API contract, model version, feature names, time cutoff, database paths, attribution, no-commit/no-test data policy, and demo walkthrough are cross-role tasks. If one role changes feature names or request schema, other roles must be informed before packaging.

## 16. Code reading guide: kaunsi file kholni aur kya dekhna

| File | Read this for |
|---|---|
| `scripts/build_waterlevel.py` | Source cleanup, spatial match, overlap, dedup. |
| `scripts/build_dataset.py` | Table joins, lags, month sin/cos, dataset versions. |
| `scripts/qc_flags.py` | QC logic and non-destructive flags. |
| `scripts/model_utils.py` | Split loader, forbidden feature guard, preprocessing, metrics, final fit. |
| `notebooks/02_baseline_no_depth.ipynb` | Modeling experiment history. Treat notebook state as exploratory, not an API. |
| `docs/decisions.md` | Chosen model, feature gate, holdout protocol, neighbor and sensitivity decisions. |
| `models/v2/feature_list.json` | Exact serving input contract. |
| `models/v2/metrics.json` | Final metrics/config and scope. |
| `backend/app/services/feature_service.py` | Resolve coordinates and construct model inputs. |
| `backend/app/services/model_service.py` | Load and invoke frozen model, residual interval. |
| `backend/app/routers/predict.py` | API glue, band/warnings and response logging. |
| `backend/app/db.py` | CSV-to-SQLite table import and runtime tables. |
| `backend/app/services/geocoding_service.py` | Place search cache, throttling, Rajasthan checks. |
| `frontend/streamlit_app.py` | Actual visible pages, forms, API requests, output labels. |
| `backend/tests/` | Expected behavior contracts (tests last ran 9 passed on 2026-11-01). |

When opening code, trace one question at a time. Example: “Where does coordinates become neighbors?” -> selected result in Streamlit -> POST payload -> `PredictRequest` -> `FeatureService.resolve_target` -> distance sort -> prior reading SQL -> model feature dict -> `ModelService.predict` -> response table.

## 17. Current status and what remains

As of 2026-11-02, the project has a working local Demo 2 path from place selection to a model result. That is a demo milestone, not the final research submission.

### Kaam jo ho chuka hai

| Workstream | Complete so far | Evidence/status |
|---|---|---|
| Role 1 - Data | Station readings, station locations, rainfall and block information were assembled into versioned data; quality checks, joins, IDs, dates, units and modeling columns were documented. | Current dataset has 92,452 rows and 77 columns; the model uses the 2005-2023 window. See the data scripts, dataset notes and decisions log. |
| Role 2 - Model | Baselines and feature groups were compared; station-group and district validation were used; v2 Random Forest was frozen with 10 inputs. | New-station CV MAE 7.531 m; new-district CV MAE 9.037 m; known-station 2022-23 temporal test MAE 3.205 m. |
| Neighbor feature audit | The old generator could not be recovered, so a written v3 reconstruction was implemented and audited without changing the frozen model. | Reconstructed v3 passed the new-station gate (MAE 7.501 m); original stored count still differs on about 2.2% of rows. |
| Backend | FastAPI endpoints, SQLite import, model loading, prediction, neighbor evidence, advisory, trends and health checks are implemented. | On 2026-11-01 the API test suite reported 9 passed, 2 dependency deprecation warnings; local health and a prediction smoke check worked. |
| Frontend | Streamlit pages connect to the API for overview, station map, searched-place prediction, advisory, trends and model limitations. | Local app returned HTTP 200; a searched Nareli/Ajmer example returned five nearby observations and a prediction. |
| Integration | The local database, API, model artifact and UI have been connected for a supervised walkthrough. | On 2026-11-02 the launch script started both services; `/health` reported model v2/database ready and Streamlit returned HTTP 200. These are local checks, not deployment or validation for every place. |

Model results ka sahi matlab: new-station CV MAE 7.531 m unfamiliar stations ka sabse relevant measured score hai. New-district CV MAE 9.037 m aur zyada unfamiliar geography ka harder check hai. Temporal MAE 3.205 m un stations par hai jo training mein pehle se the; ise new-location accuracy mat bolo. Seen-station temporal split par persistence baseline MAE 2.648 m tha, lekin persistence ko aise naye place par same-station ki purani reading chahiye hoti jo wahan maujood nahi.

2024 Jan/May holdout ka one-time result: combined n=742, MAE 4.050 m, RMSE 7.121 m, R² 0.9020. January n=668 MAE 3.870 m; May n=74 MAE 5.667 m. Saare holdout stations training/validation station list mein the; isliye unseen-station subgroup n=0. Ye known-station temporal check hai, new-location accuracy nahi. Is score ke baad koi tuning nahi hui.

Interval par alag kaam hua: train-only v3 features par GroupKFold OOF se candidate residual table banaya. Cross-fit coverage diagnostic 79.91% pooled, fold mean width roughly 23.9 m tha. Ye candidate `docs/results/interval_v3_candidate.json` mein hai; **live table replace nahi hui**, isliye app abhi bhi historical-neighbor calibration warning dikhata hai. Candidate ka cross-fit number independent external guarantee nahi.

### Demo 2 ke liye kya tayyar hai

- Local walkthrough chal sakta hai: backend health, place search, prediction, nearby station evidence, advisory, trends aur model/limitations screens.
- Prediction ke saath range, confidence, relative depth band aur nearby observations dikhte hain. Nearby stations searched point ke aas-paas ke measurements hain, usi jagah ke direct measurements nahi.
- Demo se pehle dono services start karke `/health` check karo, ek jagah search aur prediction end-to-end chalao, aur internet ke bina geocoder fail ho sakta hai isliye screenshots/video backup rakho.
- 2022 ya 2023 ka example use karo. Jan/May 2024 rows ka one-time holdout evaluation ho chuka hai; unhe demo example ya future tuning ke liye use mat karo.
- Demo mein bolo: “This is a seasonal estimate; new-station MAE is about 7.5 m. The 2022-23 temporal score is for known stations. Neighbor inputs are a documented reconstruction. Advisory is provisional.”

### Abhi kya baaki hai

1. **2024 Jan/May holdout:** 742 rows ko 2 Nov 2026 ko ek baar score kiya. Result `docs/results/holdout_2024_jan_may_v3.json` mein hai. Saare stations known the; ise new-station accuracy mat kehna aur is holdout se tuning mat karna.
2. **Original neighbor generator:** exact purana code nahi mila. V3 reconstruction documented hai; stored neighbor count mein takriban 2.2% mismatch abhi unresolved hai. Leakage audit ko “original implementation ka proof” nahi kehna.
3. **Prediction interval:** v3 ke liye train-only OOF se candidate table bana hai, jiska pooled cross-fit coverage diagnostic 79.91% hai. Candidate live API mein activate nahi kiya; active range abhi old stored inputs par calibrated hai. Candidate ko review/regression checks ke baad hi use karna; kisi range ko guarantee ya safety interval mat kehna.
4. **Borewell advisory:** historical well-depth p75 ek reference hai. Supervisor-approved engineering buffer nahi, isliye ise safe drilling depth nahi kehna.
5. **External use:** place search public geocoder/network par depend karta hai. Wider deployment, load/security review, user testing, monitoring aur operational ownership abhi final kaam hain.
6. **Research submission:** holdout result mil gaya hai; use results, scope limitations aur comparison caveats ke saath final report mein add karna. Approved Semester 8 scope aur final presentation abhi baaki hain. Demo 2 in deliverables ka substitute nahi.
7. **Git:** worktree mein uncommitted files hain. User ke instruction ke mutabik commit nahi kiya gaya.

Cutoff sensitivity check ka sample result: request-time month-start cutoff aur training exact-date cutoff mein count 0.4% rows par alag tha; mean 6.7% rows par 0.01 m se zyada alag tha (p99 2.287 m, max 9.978 m). Frozen prediction difference ka p99 1.203 m aur max 10.627 m tha; ye sensitivity hai, accuracy estimate nahi. Is check se model ya feature rule badla nahi gaya.

## 18. Semester 8: proposed extension, approval pending

Semester 8 ka scope abhi confirmed assignment nahi hai. Complete Project Doc mein diye options ko supervisor/team se approve karna hoga. Pehle data availability aur timeline decide karo; phir ek main research extension aur ek practical system extension chuno. Neeche ka schedule planning example hai, promise nahi.

| Option | Kya karenge | Zaroori input / evaluation |
|---|---|---|
| Time-series model | Monthly/weekly sequence par LSTM/GRU (ya suitable classical time-series baseline) ko current Random Forest se compare karna. | Sufficient, consistent historical/DWLR telemetry chahiye. Time-based backtesting, same forecast horizon, baseline comparison aur station-wise error report. Data na mile to daily/weekly prediction claim nahi karna. |
| Spatial estimation | Coordinates se interpolation/map layer, jaise Kriging ya Gaussian Process, explore karna. | Quality-controlled station coordinates/readings; spatial holdout (nearby stations ko train/test mein leak na hone dena), uncertainty map aur sparse-area caveat. Map estimate ko sensor measurement na kehna. |
| Engineering extension | API/UI packaging, PostgreSQL/Docker or deployment, logging/monitoring, accessibility/Hindi UI and user testing. | Hosting/device/department requirements confirm; security, reproducible setup, response time and failure handling demonstrate. |
| Optional research question | Borewell success probability ya water quality add karna only if the team can obtain valid labels/measurements. | Success/failure-labelled borewell outcomes or lab-quality records. In data ke bina ye feature/model nahi ban sakta. |

Practical sequence: Month 1 mein supervisor se question/scope lock, data rights and data quality check; Month 2 mein data pipeline and baseline; Month 3 mein chosen time-series or spatial method and fair validation; Month 4 mein backend/UI integration and user testing; Month 5 mein error analysis, final report, paper/poster and demo. Agar DWLR data nahi milta, time-series plan ko available seasonal data ke hisaab se revise karo ya approved spatial/engineering option par shift karo.

Role division Semester 8 mein bhi clear rakho: Role 1 data source, access, cleaning, station/time coverage aur data dictionary own kare; Role 2 baselines, validation design, modeling, error analysis aur model card own kare. Backend role serving/data storage, frontend role map/workflow/user testing; sab log shared feature/API definitions and limitations approve karein. Supervisor final question, data access, success criteria aur safety wording approve kare.

Semester 8 ka aim sirf “bada model” banana nahi: ek well-defined research question ka jawab, fair unseen-time/location evaluation, reproducible code/data trail aur limitations ke saath final demo/report dena hai.

## 19. A 2-minute speaking script

“Our project estimates seasonal groundwater depth-to-water for Rajasthan. The target is WLS_WTR_LEVEL in metres below ground, so larger values mean water is deeper. Role 1 assembled and checked station water-level data with location and climate metadata. Role 2 compared feature groups using temporal validation and station/district-based cross-validation, then froze a ten-feature Random Forest. The API resolves a searched place, builds location, time, elevation and strictly prior nearby-station features, and calls that frozen model. The UI shows the estimate together with the contributing stations and warnings. For a new station, GroupKFold MAE is 7.531 metres; the 2022-23 temporal MAE of 3.205 metres is for stations already seen in training, not new locations. Neighbor values use a documented reconstruction because the original generator was not recovered. The saved range has not been recalibrated for the reconstruction, and borewell advice is provisional rather than a safety guarantee.”

## 20. Quick revision checklist before viva

- Can I explain depth-to-water versus well depth without mixing them?
- Can I draw the raw data -> Role 1 -> Role 2 -> model artifact -> API -> UI flow?
- Can I name all ten model inputs and the important excluded columns?
- Can I say why random row split is unsafe and distinguish new-station CV from temporal test?
- Can I translate MAE/R2 into plain language and give the correct scope of each score?
- Can I explain neighbor selection and say “reconstruction, not recovered original”?
- Can I identify the displayed interval warning and the advisory safety limitation?
- Can I show a location search result, its coordinates and nearby stations used?
- Can I show which code file performs each step?
- Can I state the one-time 2024 holdout result and explain why it is only known-station temporal performance?

## 21. Code ko chhote examples se samjho

Ye snippets samajhne ke liye chhote kiye hain; poore production function ki jagah nahi lete.

### Role 1: duplicate ko chupke se mat hatao

```python
if v0.duplicated(KEYS, keep=False).any():
    raise ValueError("Repeated station-date key; resolve explicitly")
```

`KEYS` `SITE_ID` aur `DATE` hain. `duplicated(..., keep=False)` dono copies mark karta hai. `raise` pipeline ko rokta hai taaki team duplicate ka source samjhe; `drop_duplicates()` se bina decision data gayab nahi hota.

### Role 1: pichhli same-station reading ka lag

```python
v2 = v2.sort_values(["SITE_ID", "DATE"])
previous = v2.groupby("SITE_ID")["WLS_WTR_LEVEL"].shift(1)
```

Pehle station aur date order zaroori hai. `groupby` har station ki alag history banata hai; `shift(1)` har row ko usi station ki previous row deta hai. Freeze model mein ye lag feature nahi hai, kyunki unseen location ke paas usi SITE_ID ki history nahi hoti.

### Role 2: season ko circle banana

```python
month_sin = sin(2 * pi * month / 12)
month_cos = cos(2 * pi * month / 12)
```

Sine aur cosine saath milkar saal ke cycle par month ki jagah batate hain. Isse December aur January circle par neighbor months rehte hain. Sirf month number dene par model 12 aur 1 ko 11 units door dekh sakta hai.

### Neighbor search: cutoff se pehle wali aakhri reading

```python
position = searchsorted(sorted_dates, cutoff, side="left")
previous_index = position - 1
```

Sorted dates mein `left` insertion point cutoff ke barabar date se pehle aata hai; `-1` karke strictly earlier reading milti hai. Exact date cutoff offline builder mein hota hai; API month/year request mein first day cutoff SQL condition `date < target_day` se hoti hai. Ye chhota difference isi liye audit hua.

### Backend: exact feature list, phir predict

```python
missing = [name for name in feature_list if name not in values]
if missing:
    raise ValueError("Required features missing")
row = DataFrame([{name: values[name] for name in feature_list}])
prediction = model.predict(row)
```

Model ko wahi columns chahiye jo training mein the, naam aur order sahit. Missing feature par chupke se arbitrary value nahi daali jati. DataFrame banane ke baad frozen sklearn pipeline apna preprocessing aur Random Forest prediction chalati hai.

### Viva practice: request ko trace karo

Apne words mein ye chain bolkar practice karo: `streamlit_app.py` selected place ki lat/lon leta hai -> JSON `POST /predict` banta hai -> `PredictRequest` ranges/required pair check karta hai -> `FeatureService` target resolve karke neighbors/season/elevation banata hai -> `ModelService` required features aur artifact check karke prediction leta hai -> router risk/range/warnings aur source stations jodta hai -> Streamlit metres aur evidence table dikhata hai. Har arrow par batao kaunsa file/function kaam karta hai.

