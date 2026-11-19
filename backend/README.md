# Demo 2 FastAPI backend

This implements the 7th-semester backend scope: FastAPI, SQLite, frozen model inference, request-time neighbor features, advisory/history endpoints, validation, CORS, Swagger, and pytest coverage.

## Run from the repository root

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
python -m backend.scripts.init_db
uvicorn backend.app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`. SQLite is created at `backend/data/groundwater.sqlite3` from `data/processed/*.csv`. The import script is safe to rerun; it refreshes the derived tables from those source CSVs. Set `GW_AUTO_INIT_DB=0` to prevent automatic initialization on API startup.

## Endpoints

| Method and path | Purpose |
|---|---|
| `GET /health` | API, database, and frozen model status |
| `GET /districts` | District dropdown options |
| `GET /blocks?district=Ajmer` | Mapped blocks for one district |
| `GET /locations/search?q=...` | Search a Rajasthan place name and return map coordinates |
| `GET /stations?district=Nagaur&block=LADNU` | Map markers and block stage; readings default to the 2023-12-31 cutoff (`as_of_date` can be supplied) |
| `GET /history?site_id=...` or `?district=...&block=...` | Water-level history and nearest-grid rainfall series |
| `POST /predict` | Frozen v2 seasonal prediction and inputs used |
| `POST /advisory` | Historical well-depth summary, stage warning, and provisional depth reference |
| `GET /model/info` | Version, feature contract, and validation context |

## Login and roles

The model artifact stays unchanged. Authentication is enforced by the API before protected data or prediction routes run. `GET /health`, `POST /auth/login`, `POST /auth/register`, and `POST /auth/complete-registration` are public; the remaining application routes require a bearer session. Roles are `user` and `admin`. Users can use the prediction, station, history, and advisory features. Admins can also review access requests, list/create/disable accounts, and view aggregate API request totals.

Public registration requires SMTP configuration. A requester submits an email, opens the one-time verification link, and sets a password of at least 12 characters. The verified request waits for administrator approval. Signup throttling allows up to three requests per email and 30 requests per service per hour. Configure `GW_SMTP_USERNAME`, `GW_SMTP_PASSWORD`, `GW_MAIL_FROM`, and `GW_ADMIN_NOTIFICATION_EMAIL`; use a Gmail App Password for Gmail SMTP. Never commit mail credentials.

Create the first administrator once, before starting the API:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.create_admin
```

The command asks for the email and password without echoing the password. Use a unique password with at least 12 characters. Passwords are stored as PBKDF2-SHA256 hashes; login failures are temporarily locked after five attempts. Successful sign-ins receive a random bearer session that expires after 12 hours. Only a hash of the session token is stored in SQLite. Signing out revokes it, and disabling an account revokes its sessions.

If an account password is forgotten or exposed, reset it locally with `.\.venv\Scripts\python.exe -m backend.scripts.reset_password`. The command asks for the account email and a new password without echoing the password, clears failed-login lockout, and signs out that account's existing sessions.

The Streamlit app keeps the session token in its server-side session state and sends it in the `Authorization: Bearer ...` header. It does not put the password in a URL or browser storage. The API performs the role check; hiding the admin menu in the UI is only a presentation choice, not the access control.

This is a local academic-demo security layer. A deployed version also needs HTTPS, secret and database backup policies, account recovery/password change, audit retention rules, and production hosting controls. Do not expose the local demo server directly to the public internet.

Example prediction request:

```json
{
  "district_name": "Nagaur",
  "block_name": "LADNU",
  "month": 5,
  "year": 2024
}
```

For station-level inputs, pass `site_id` instead. For a new location, use `/locations/search` to resolve a place name, then pass the returned district and coordinate pair (`latitude`, `longitude`) to `/predict`. The API uses the chosen coordinates rather than a district or block centroid.

## Frozen v2 input and neighbor rule

The API reads the exact ten feature names from `models/v2/feature_list.json`. Rainfall, extraction stage, rainfall scenarios, well type, and `WELL_DEPTH` are not model inputs. Month encoding is `sin(2*pi*month/12)` and `cos(2*pi*month/12)`.

Neighbor construction follows `docs/decisions.md`: exclude target `SITE_ID` when supplied; select the five nearest other stations within inclusive 40 km before checking reading availability; for those five, use each station's latest reading strictly before the first day of the requested month. There is no age cutoff and no replacement from the sixth neighbor. Mean and distance are null when no readings qualify, count is zero. `/predict` returns these source stations and their distances/reading dates alongside summary statistics. Only pre-target readings are used.

Place-name search uses the public OpenStreetMap Nominatim service for direct user searches only. Search results are restricted to Rajasthan, cached for 90 days in SQLite, and requests are throttled to at most one per second. The app displays OpenStreetMap attribution and a notice before the user submits a place. The geocoder endpoint is configurable with `GW_GEOCODER_URL`; switch providers if Nominatim requests this. See the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/) before deploying beyond this small demo.

## Important model and advisory limits

- This is a seasonal prediction, not a daily forecast. `YEAR` is trained on 2005–2023; later years produce an extrapolation warning.
- A district or block request uses the mean coordinates and elevation of mapped stations as a representative location. Place-search predictions instead use the selected place's geocoded coordinates and return nearby observed station readings; these are area references, not readings at the searched address.
- The supplied interval table predates reconstructed neighbor_v3 inputs. It is returned with an explicit calibration warning and must not be presented as validated 80% coverage for this inference path.
- `/advisory` reports historical `WELL_DEPTH` distribution and the p75 as a provisional reference. A recommended drilling depth is not engineering assurance. Configure `GW_ADVISORY_BUFFER_M` only after supervisor approval; when configured, the API uses the larger of historical p75 and predicted level plus that buffer.
- The model loader fails closed. A missing or incompatible frozen model yields `/health` degraded and `/predict` 503; it never substitutes a dummy or mean prediction.
- Prediction inputs and responses are stored in `prediction_log` for the demo. Do not expose personal data; this project currently logs only API payloads.

## Tests

From the repository root run `pytest backend/tests -q`. Tests cover the feature contract, strict prior-reading rule, neighbor selection, validation and SQLite import behavior.
