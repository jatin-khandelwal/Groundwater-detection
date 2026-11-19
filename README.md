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

### Neighbor feature rule

The original historical neighbor generator was not recovered. The project documents and implements a reconstruction: exclude the target station when its ID is known; choose the five nearest other stations within 40 km inclusive before checking reading availability; use each selected station’s latest reading strictly before the first day of the requested month; apply no age limit and do not replace a selected station with the sixth neighbor. The app shows the stations and reading dates used. The saved prediction range has not been recalibrated for this reconstructed request-time input path.

## Application architecture

- **Frontend:** Streamlit dashboard with Overview, Stations, Prediction, Advisory, Trends, Model and data, account, and administration views.
- **Backend:** FastAPI service with SQLite, frozen-model inference, validation, and protected user/admin endpoints.
- **Place lookup:** OpenStreetMap Nominatim. A working internet connection is needed for new place searches; the prediction and stored-data pages use the project database.
- **Deployment:** Separate Render web services described by [`render.yaml`](render.yaml). See [`docs/FREE_RENDER_DEPLOY.md`](docs/FREE_RENDER_DEPLOY.md).

The API exposes `/health`, `/districts`, `/blocks`, `/stations`, `/locations/search`, `/history`, `/model/info`, `/predict`, and `/advisory`. Authentication and administration routes are documented in the interactive API docs.

### Accounts and security

Users submit an access request, verify their email, set a password, and wait for administrator approval. Signup is limited to three requests per email and 30 requests per service per hour. Passwords use salted PBKDF2-SHA256 hashes; login attempts are temporarily locked after repeated failures; sessions expire after 12 hours. Email verification and notifications require the SMTP environment variables documented in `render.yaml` and `docs/FREE_RENDER_DEPLOY.md`.

This is a supervised academic demo, not a production groundwater or drilling-safety service. Render Free uses temporary SQLite storage. Before wider public use, move accounts to persistent storage and add IP-based signup throttling, CAPTCHA, account recovery, and a reviewed advisory buffer.

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
