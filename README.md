# Rajasthan Groundwater Intelligence and Borewell Advisory

A B.Tech project that combines historical groundwater observations with a frozen machine-learning model and a web application. The system estimates seasonal depth to water for a selected Rajasthan location and shows nearby observations and a provisional borewell-depth reference.

> **Interpretation:** Water level is measured as depth below ground. A larger value means water is deeper. Predictions are area estimates, not measurements at the searched address, and the advisory is not a drilling-safety guarantee.

## Live demo

- **Frontend:** [groundwater-frontend.onrender.com](https://groundwater-frontend.onrender.com)
- **Backend API:** [groundwater-api-pgfo.onrender.com](https://groundwater-api-pgfo.onrender.com)
- **API documentation:** [Interactive API docs](https://groundwater-api-pgfo.onrender.com/docs)

Render Free services sleep after inactivity and can take time to wake. Their local SQLite storage is temporary, so accounts and sessions can reset after a restart or redeploy.

## What the application does

- Search for a place in Rajasthan or provide coordinates, then request a month-and-year prediction.
- Build request-time inputs from the selected location and nearby monitoring stations.
- Show the estimate, a prediction range, confidence, warnings, and the source stations used.
- Explore station locations, historical groundwater readings, rainfall history, and model validation results.
- Provide a historical well-depth distribution as a provisional reference.
- Require sign-in for protected features. An administrator can review verified access requests and manage accounts.

Rainfall and extraction-stage data were collected for project analysis, but they are **not inputs to the frozen v2 model**.

## Data

The main modeling table, `dataset_v2_3.csv`, contains 92,452 observations from 1,403 stations across 33 districts. The modeling period is 2005–2023. Supporting project tables include monthly NASA POWER climate data, station coordinates and elevation, and a 2023 groundwater extraction-stage snapshot.

| Data | Source or method |
|---|---|
| Groundwater level | Central Ground Water Board monitoring records and India Data Portal / India-WRIS records |
| Rainfall and climate | [NASA POWER](https://power.larc.nasa.gov/) monthly grid data |
| Elevation | SRTM30 elevation, queried through OpenTopoData |
| Extraction stage | CGWB and Rajasthan groundwater department assessment tables |
| Place search | [OpenStreetMap Nominatim](https://operations.osmfoundation.org/policies/nominatim/) |

The repository does not contain the full processed datasets or the original scikit-learn model binary. Obtain those files from the project’s approved data/model archive for local reproduction. Render downloads its compact, unchanged model artifact from the public `render-artifacts-v2` branch during startup.

The 77-column dataset dictionary is at [`docs/data_dictionary_dataset_v2_3.csv`](docs/data_dictionary_dataset_v2_3.csv). Dataset decisions and limitations are in [`docs/decisions.md`](docs/decisions.md) and [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

### Data preparation and integration

The pipeline standardizes station identifiers, dates, coordinates, and measurement fields; checks duplicates and implausible values; and keeps manual, GPRS, and above-mean-sea-level (AMSL) records distinguishable. Source station records were reconciled using station metadata and geographic distance; the documented candidate-link threshold was 0.2 km. The main modeling table uses manual observations. Rainfall and climate tables are aligned by month and grid cell, elevation by station location, and groundwater extraction-stage context by block. These supporting tables are useful for analysis and the interface, but only elevation from those sources is a feature in frozen v2.

The database contains 1,403 stations, 92,452 water-level readings, 36,288 monthly rainfall records, and 302 block-statistics records. A station can have many dated readings. Dataset preparation and model scripts use Python with pandas and NumPy; model training and evaluation use scikit-learn.

## Model and evaluation

The deployed model is a frozen 10-input Random Forest. Its target is seasonal depth to water in metres. Its inputs are district, latitude, longitude, year, month sine/cosine, elevation, and three reconstructed neighbor summaries: mean prior level, nearest contributing distance, and contributing count.

| Evaluation setting | R² | MAE | MedAE | Scope |
|---|---:|---:|---:|---|
| New-station GroupKFold | 0.6902 | 7.531 m | 4.547 m | Stations held out by station ID |
| New-district leave-one-district-out | 0.5868 | 9.037 m | 5.877 m | Districts held out in turn |
| 2022–2023 temporal test | 0.9411 | 3.205 m | 2.067 m | Stations already seen during training |
| 2024 January/May one-time holdout | 0.9020 | 4.050 m | — | 742 rows, all from stations seen during training; evaluated once with reconstructed neighbors |

MAE is the average absolute error in metres. R² is not an accuracy percentage. The temporal scores do not measure performance at new locations; use the new-station and new-district evaluations for that question. The 2024 holdout has already been evaluated and must not be reused for model selection.

Random Forest and XGBoost were first compared as 26-feature candidates using the same new-station validation setup: MAE 7.459 m and 7.598 m, respectively. The final model was then refit as a 10-feature Random Forest. Its settings and metrics are in [`models/v2/metrics.json`](models/v2/metrics.json); its exact feature list is in [`models/v2/feature_list.json`](models/v2/feature_list.json).

The frozen Random Forest uses 100 trees, maximum depth 20, `max_features=0.4`, `min_samples_leaf=1`, and random seed 42. A train-mean baseline had an MAE of about 17.5 m. A persistence baseline had a 2.648 m temporal-test MAE, but it requires prior observations for the same station and is not an equivalent method for a new location. Baselines therefore answer different questions and should not be compared without stating their evaluation scope.

**Metric guide:** MAE is the mean absolute prediction error in metres; MedAE is the median absolute error and is less affected by a few large misses; RMSE squares errors before averaging and therefore penalizes large misses more; R² compares explained variation with a constant-mean baseline. R² is not an accuracy percentage. GroupKFold keeps all observations from a held-out station together, while leave-one-district-out validation holds out a whole district. Temporal evaluation holds out later dates and measures performance at stations represented during training.

### Neighbor feature rule

The original historical neighbor generator was not recovered. The project documents and implements a reconstruction: exclude the target station when its ID is known; choose the five nearest other stations within 40 km inclusive before checking reading availability; use each selected station’s latest reading strictly before the first day of the requested month; apply no age limit and do not replace a selected station with the sixth neighbor. The app shows the stations and reading dates used. The saved prediction range has not been recalibrated for this reconstructed request-time input path.

## Application architecture

- **Frontend:** Streamlit dashboard with Overview, Stations, Prediction, Advisory, Trends, Model and data, account, and administration views.
- **Backend:** FastAPI service with SQLite, frozen-model inference, validation, and protected user/admin endpoints.
- **Place lookup:** OpenStreetMap Nominatim. A working internet connection is needed for new place searches; the prediction and stored-data pages use the project database.
- **Deployment:** Separate Render web services described by [`render.yaml`](render.yaml). See [`docs/FREE_RENDER_DEPLOY.md`](docs/FREE_RENDER_DEPLOY.md).

The API exposes `/health`, `/districts`, `/blocks`, `/stations`, `/locations/search`, `/history`, `/model/info`, `/predict`, and `/advisory`. Authentication routes support login, registration/access requests, registration completion, current-user lookup, and logout. Administrator routes list users and access requests, approve or reject requests, create or update users, and show administrative activity. The complete request and response schemas are available at `/docs`.

For a prediction, the frontend sends the selected coordinates and target month/year to FastAPI. The backend validates the request, resolves elevation and prior nearby-station readings from stored data, applies the model’s expected feature order, and returns the estimate, range, confidence, warnings, and contributing-station details. The nearby readings are evidence for a regional estimate; they are not a measurement at the searched address. The advisory endpoint separately summarizes historical well-depth records and block extraction-stage context.

### Accounts and security

Users submit an access request, verify their email, set a password, and wait for administrator approval. Signup is limited to three requests per email and 30 requests per service per hour. Passwords use salted PBKDF2-SHA256 hashes; login attempts are temporarily locked after repeated failures; sessions expire after 12 hours. Email verification and notifications require the SMTP environment variables documented in `render.yaml` and `docs/FREE_RENDER_DEPLOY.md`.

This is a supervised academic demo, not a production groundwater or drilling-safety service. Render Free uses temporary SQLite storage. Before wider public use, move accounts to persistent storage and add IP-based signup throttling, CAPTCHA, account recovery, and a reviewed advisory buffer.

### Known model and service limitations

- New-station and new-district errors are higher than known-station temporal errors; use the validation row matching the intended use case.
- The original historical neighbor-feature generator was not recovered. The implemented rule is a documented reconstruction, and the saved prediction interval has not been recalibrated for request-time reconstructed inputs.
- The neighbor rule has no maximum reading-age cutoff. The interface reports contributing stations and dates so users can inspect the context.
- The model was trained on 2005–2023 data. Predictions for later years are extrapolations and should be treated cautiously.
- Place-name search depends on Nominatim and network availability. Stored station history and prediction data are separate from that external geocoding service.
- Borewell depth is a historical reference distribution, not a geotechnical assessment or drilling-safety recommendation.
- The 2024 January/May holdout has already been evaluated once. It must remain closed to model selection; future model changes require a new later holdout.

## Run locally

Use Windows PowerShell from the repository root. Local runtime data and model files are not included in this Git repository; obtain the approved project archive first.

```powershell
# Run this from the folder where you cloned the repository.
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m pip install -r frontend\requirements.txt
```

With the processed CSVs in `data\processed\` and the frozen model files under `models\v2\`, initialize the local database:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.init_db
```

Open two PowerShell windows from the project root. Start the backend in the first:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

Start the frontend in the second:

```powershell
.\.venv\Scripts\python.exe -m streamlit run frontend\streamlit_app.py
```

Open `http://localhost:8501`. The API documentation is at `http://127.0.0.1:8000/docs`. To create a local administrator, run `.\.venv\Scripts\python.exe -m backend.scripts.create_admin` and follow the prompts. For local email-based sign-up, configure the SMTP environment variables first.

## Repository structure

```text
backend/          FastAPI application, SQLite schema, and service modules
frontend/         Streamlit application
models/v2/        Small model metadata; the model binary is excluded from Git
data/             Source and processed data; large files are excluded from Git
scripts/          Dataset, feature, model, and audit utilities
docs/             Decisions, metrics, limitations, reports, and figures
render.yaml       Render Blueprint for the two hosted services
```

## Verify changes

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

## Report figures

Prepared figures and source notes are in [`docs/figures/`](docs/figures/). The figure guide explains each figure’s scope and cautions against interpreting candidate-model charts as final-model results.
