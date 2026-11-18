from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import httpx
import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API_URL = os.getenv("GW_API_URL", "http://127.0.0.1:8000")
HISTORY_CUTOFF = date(2023, 12, 31)


class BackendError(RuntimeError):
    pass


@st.cache_resource
def get_http_client() -> httpx.Client:
    request_timeout = float(os.getenv("GW_API_TIMEOUT_SECONDS", "12"))
    connect_timeout = float(os.getenv("GW_API_CONNECT_TIMEOUT_SECONDS", "3"))
    return httpx.Client(
        timeout=httpx.Timeout(request_timeout, connect=connect_timeout),
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    )


def request_api(method: str, base_url: str, path: str, *, params=None, payload=None, authenticated: bool = True):
    headers = {}
    token = st.session_state.get("auth_token") if authenticated else None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = get_http_client().request(
            method, f"{base_url.rstrip('/')}{path}", params=params, json=payload, headers=headers
        )
    except httpx.HTTPError as exc:
        raise BackendError(f"Cannot connect to the backend: {exc}") from exc
    if response.is_error:
        try:
            details = response.json().get("detail", response.text)
        except ValueError:
            details = response.text
        raise BackendError(f"API {response.status_code}: {details}")
    return response.json()


@st.cache_data(ttl=15, max_entries=4)
def get_health(base_url: str):
    return request_api("GET", base_url, "/health")


@st.cache_data(ttl=300, max_entries=100)
def cached_get(base_url: str, path: str, params_json: str = "{}", token: str = ""):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        response = get_http_client().get(
            f"{base_url.rstrip('/')}{path}", params=json.loads(params_json), headers=headers
        )
    except httpx.HTTPError as exc:
        raise BackendError(f"Cannot connect to the backend: {exc}") from exc
    if response.is_error:
        try:
            details = response.json().get("detail", response.text)
        except ValueError:
            details = response.text
        raise BackendError(f"API {response.status_code}: {details}")
    return response.json()


def get_json(base_url: str, path: str, params=None):
    return cached_get(
        base_url, path, json.dumps(params or {}, sort_keys=True),
        st.session_state.get("auth_token", ""),
    )


@st.cache_data
def load_ablation_table(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def show_api_error(error: Exception):
    st.error(str(error))
    st.caption("Check that the backend is running at the configured URL.")


def clear_prediction_result():
    st.session_state["prediction_result"] = None


def load_districts(base_url: str) -> list[str]:
    return get_json(base_url, "/districts").get("districts", [])


def load_blocks(base_url: str, district: str) -> list[str]:
    return get_json(base_url, "/blocks", {"district": district}).get("blocks", [])


def select_area(base_url: str, prefix: str, *, require_block: bool = False):
    districts = load_districts(base_url)
    if not districts:
        st.warning("No districts were returned by the API.")
        return None, None
    district = st.selectbox("District", districts, key=f"{prefix}_district")
    blocks = load_blocks(base_url, district)
    if require_block:
        if not blocks:
            st.warning("No mapped blocks are available for this district.")
            return district, None
        return district, st.selectbox("Block", blocks, key=f"{prefix}_block")
    options = ["District representative location"] + blocks
    selected = st.selectbox("Block", options, key=f"{prefix}_block")
    return district, None if selected == options[0] else selected


def render_overview(model_info: dict):
    st.header("Groundwater intelligence")
    st.write("Seasonal groundwater-level prediction and historical borewell-depth reference for Rajasthan.")
    validation = model_info.get("validation", {})
    new_station = validation.get("new_station", {})
    new_district = validation.get("new_district", {})
    temporal = model_info.get("temporal_test", {})
    cols = st.columns(3)
    cols[0].metric("New-station CV MAE", f"{new_station.get('MAE', '—')} m", border=True)
    cols[1].metric("New-district CV MAE", f"{new_district.get('MAE', '—')} m", border=True)
    cols[2].metric("2022–23 temporal MAE", f"{temporal.get('MAE', '—')} m", border=True)
    with st.container(border=True):
        st.markdown("**How to read these results**")
        st.caption("The 2022–23 test uses stations seen during training. Use the new-station and new-district CV results to understand performance in unfamiliar areas.")
        st.caption("Water level is depth to water: larger values mean water is farther below ground.")


@st.fragment
def render_map(base_url: str):
    st.header("Monitoring stations")
    try:
        district, block = select_area(base_url, "map")
        params = {"as_of_date": HISTORY_CUTOFF.isoformat(), "limit": 5000}
        if district:
            params["district"] = district
        if block:
            params["block"] = block
        result = get_json(base_url, "/stations", params)
    except BackendError as exc:
        show_api_error(exc)
        return

    stations = result.get("stations", [])
    st.caption(f"{len(stations):,} stations · observations through {result.get('as_of_date', HISTORY_CUTOFF)}")
    if not stations:
        st.info("No mapped stations were found for this selection.")
        return
    frame = pd.DataFrame(stations)
    points = frame.dropna(subset=["latitude", "longitude"])[["latitude", "longitude"]]
    if not points.empty:
        st.map(points.rename(columns={"latitude": "lat", "longitude": "lon"}))
    columns = [
        "site_id", "station_name", "district_name", "block_name", "latitude", "longitude",
        "latest_level_m", "latest_date", "block_stage_pct", "block_stage_category",
    ]
    st.dataframe(frame[[column for column in columns if column in frame.columns]], hide_index=True)


@st.fragment
def render_prediction(base_url: str, health: dict):
    st.header("Seasonal prediction")
    st.caption("The frozen v2 model does not use well depth, well type, or a rainfall scenario as input.")
    if not health.get("model_loaded"):
        st.error("The frozen v2 model is unavailable.")
        return
    st.session_state.setdefault("prediction_search_id", 0)
    with st.form("location_search_form", border=False):
        query = st.text_input(
            "Location in Rajasthan",
            placeholder="Type a place, address, college, village, or landmark",
            max_chars=200,
        )
        search_submitted = st.form_submit_button("Find location", icon=":material/search:")
    st.markdown("Place search is sent to OpenStreetMap Nominatim. Avoid entering private details. [© OpenStreetMap contributors](https://www.openstreetmap.org/copyright).")

    if search_submitted:
        if len(query.strip()) < 3:
            st.session_state["prediction_locations"] = []
            st.session_state["prediction_result"] = None
            st.warning("Enter at least 3 characters to search.")
        else:
            with st.spinner("Searching Rajasthan locations…"):
                try:
                    response = request_api("GET", base_url, "/locations/search", params={"q": query.strip()})
                except BackendError as exc:
                    show_api_error(exc)
                    return
            st.session_state["prediction_locations"] = response.get("results", [])
            st.session_state["prediction_result"] = None
            st.session_state["prediction_search_id"] += 1
            if not st.session_state["prediction_locations"]:
                st.info("No matching Rajasthan place was found. Try a nearby town, village, or landmark name.")

    locations = st.session_state.get("prediction_locations", [])
    if not locations:
        st.info("Search for a place to begin. The app will use its coordinates and nearby groundwater stations.")
        return

    location_index = st.selectbox(
        "Choose the matching place",
        range(len(locations)),
        format_func=lambda index: locations[index]["label"],
        key=f"prediction_location_choice_{st.session_state['prediction_search_id']}",
        on_change=clear_prediction_result,
    )
    selected_location = locations[location_index]
    if selected_location.get("district_source") == "nearest_station_admin_area":
        st.warning("The place search did not identify a matching district; the nearest mapped station's district is used for the model.")

    with st.form("prediction_form", border=True):
        left, right = st.columns(2)
        month = left.selectbox("Target month", list(range(1, 13)), index=date.today().month - 1)
        year = right.number_input("Target year", min_value=2005, max_value=2100, value=date.today().year, step=1)
        submitted = st.form_submit_button("Predict groundwater level", type="primary")

    if submitted:
        payload = {
            "district_name": selected_location["district_name"],
            "latitude": selected_location["latitude"],
            "longitude": selected_location["longitude"],
            "month": int(month),
            "year": int(year),
        }
        with st.spinner("Building nearby-station features and requesting prediction…"):
            try:
                result = request_api("POST", base_url, "/predict", payload=payload)
            except BackendError as exc:
                show_api_error(exc)
                return
        st.session_state["prediction_result"] = result
        st.session_state["prediction_result_location"] = selected_location["label"]

    result = st.session_state.get("prediction_result")
    if not result:
        return
    interval = result.get("interval", {})
    st.caption(f"Prediction location: {st.session_state.get('prediction_result_location', selected_location['label'])}")
    cols = st.columns(3)
    cols[0].metric("Predicted depth to water", f"{result['prediction_m']:.2f} m", border=True)
    cols[1].metric("Relative depth band", result.get("risk", "—").title(), border=True)
    cols[2].metric("Confidence", result.get("confidence", "low").title(), border=True)
    st.write(f"Model range: **{interval.get('lower_m', '—')}–{interval.get('upper_m', '—')} m**")
    if interval.get("calibration_status", "").startswith("historical_neighbor_inputs"):
        st.warning("The saved range was calibrated with the previous stored neighbor inputs, not reconstructed neighbor_v3 inputs.")
    for warning in result.get("warnings", []):
        st.warning(warning)

    summary = result.get("nearby_summary", {})
    st.subheader("Nearby groundwater observations")
    st.caption("Latest available readings strictly before the target month. These are nearby station observations, not measurements at the searched place.")
    stats = st.columns(6)
    stats[0].metric("Stations used", summary.get("count", 0))
    stats[1].metric("Mean level", f"{summary['mean_level_m']:.2f} m" if summary.get("mean_level_m") is not None else "—")
    stats[2].metric("Median level", f"{summary['median_level_m']:.2f} m" if summary.get("median_level_m") is not None else "—")
    stats[3].metric("Shallowest", f"{summary['min_level_m']:.2f} m" if summary.get("min_level_m") is not None else "—")
    stats[4].metric("Deepest", f"{summary['max_level_m']:.2f} m" if summary.get("max_level_m") is not None else "—")
    stats[5].metric("Nearest reading", f"{summary['nearest_distance_km']:.2f} km" if summary.get("nearest_distance_km") is not None else "—")
    if (summary.get("min_level_m") is not None and summary.get("max_level_m") is not None
            and summary["max_level_m"] - summary["min_level_m"] >= 30):
        st.warning(
            "Nearby readings vary widely. The prediction is an area estimate; review the station distances and dates below before interpreting it."
        )
    neighbor_rows = result.get("nearby_stations", [])
    if neighbor_rows:
        table = pd.DataFrame(neighbor_rows).rename(columns={
            "station_name": "Station", "district_name": "District", "block_name": "Block",
            "distance_km": "Distance (km)", "reading_date": "Reading date",
            "level_m": "Depth to water (m)", "contributed_to_model": "Used by model",
        })
        for column in ["Station", "District", "Block", "Reading date"]:
            if column in table:
                table[column] = table[column].fillna("—")
        visible = [column for column in ["Station", "District", "Block", "Distance (km)", "Reading date", "Depth to water (m)", "Used by model"] if column in table]
        st.dataframe(table[visible], hide_index=True)
    else:
        st.info("No monitoring stations are mapped within 40 km of this place, so the model has no nearby readings to use.")
    with st.expander("Model inputs", icon=":material/tune:"):
        st.json(result.get("inputs_used", {}))
    st.caption("The model was trained on 2005–2023 data; predictions for later years have limited year extrapolation.")


@st.fragment
def render_advisory(base_url: str, health: dict):
    st.header("Borewell advisory")
    st.caption("Historical well-depth distribution is shown as a provisional reference, not a drilling-safety guarantee.")
    try:
        district, block = select_area(base_url, "advisory", require_block=True)
        with st.form("advisory_form", border=True):
            left, right = st.columns(2)
            month = left.selectbox("Target month", list(range(1, 13)), index=date.today().month - 1, key="advisory_month")
            year = right.number_input("Target year", min_value=2005, max_value=2100, value=date.today().year, step=1, key="advisory_year")
            submitted = st.form_submit_button("Get advisory", type="primary", disabled=block is None)
    except BackendError as exc:
        show_api_error(exc)
        return

    if submitted and block:
        payload = {"district_name": district, "block_name": block, "month": int(month), "year": int(year)}
        with st.spinner("Preparing advisory…"):
            try:
                result = request_api("POST", base_url, "/advisory", payload=payload)
            except BackendError as exc:
                show_api_error(exc)
                return
        depths = result["historical_well_depth"]
        cols = st.columns(3)
        cols[0].metric("Provisional depth reference", f"{result['recommended_depth_m']:.2f} m", border=True)
        cols[1].metric("Confidence", result["confidence"].title(), border=True)
        cols[2].metric("Historical wells", depths["count"], border=True)
        st.caption(f"Method: {result['method']}")
        with st.expander("Depth distribution and extraction status"):
            st.json({"historical_well_depth": depths,
                     "predicted_water_level_m": result["predicted_water_level_m"],
                     "buffer_m": result["buffer_m"], "extraction_stage": result["extraction_stage"]})
        for warning in result.get("warnings", []):
            st.warning(warning)
        if not health.get("model_loaded"):
            st.info("Model unavailable; predicted water level was not included in this advisory.")


@st.fragment
def render_trends(base_url: str):
    st.header("Historical trends")
    try:
        district, block = select_area(base_url, "trend")
        left, right = st.columns(2)
        start = left.date_input("Start date", value=date(2005, 1, 1), min_value=date(1970, 1, 1), max_value=HISTORY_CUTOFF)
        end = right.date_input("End date", value=HISTORY_CUTOFF, min_value=date(1970, 1, 1), max_value=HISTORY_CUTOFF)
        if start > end:
            st.error("Start date must be on or before end date.")
            return
        params = {"start_date": start.isoformat(), "end_date": end.isoformat()}
        if district:
            params["district"] = district
        if block:
            params["block"] = block
        result = get_json(base_url, "/history", params)
    except BackendError as exc:
        show_api_error(exc)
        return

    levels = pd.DataFrame(result.get("water_levels", []))
    rainfall = pd.DataFrame(result.get("rainfall", []))
    if not levels.empty:
        levels["date"] = pd.to_datetime(levels["date"])
        levels["year"] = levels["date"].dt.year
        annual_levels = levels.groupby("year")["level_m"].mean().round(2)
        annual_levels.index = annual_levels.index.astype(str)
        st.subheader("Annual mean water level")
        st.caption(result.get("unit_note", ""))
        st.line_chart(annual_levels)
    else:
        st.info("No water-level readings were found for this period.")
    if not rainfall.empty:
        rainfall["date"] = pd.to_datetime(rainfall["date"])
        rainfall["year"] = rainfall["date"].dt.year
        annual_rainfall = rainfall.groupby("year")["rainfall_mm"].sum().round(1)
        annual_rainfall.index = annual_rainfall.index.astype(str)
        st.subheader("Annual rainfall at the nearest grid cell")
        st.caption(f"Grid: {result.get('rainfall_grid')}")
        st.bar_chart(annual_rainfall)
    else:
        st.info("No rainfall records were found for this period.")


def render_model_info(model_info: dict):
    st.header("Model and validation")
    st.caption(f"Version {model_info.get('model_version')} · {model_info.get('dataset')}")
    validation = model_info.get("validation", {})
    rows = []
    for label, key in [
        ("New station · GroupKFold", "new_station"),
        ("New district · leave-one-district-out", "new_district"),
        ("New year · existing stations", "new_year_old_stations_val2021"),
    ]:
        metrics = validation.get(key, {})
        if metrics:
            rows.append({"Validation": label, "R²": metrics.get("R2"), "MAE (m)": metrics.get("MAE"), "MedAE (m)": metrics.get("MedAE")})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True)
    st.caption(model_info.get("temporal_test_scope", ""))
    with st.expander("Frozen model features"):
        st.code("\n".join(model_info.get("features", [])), language="text")
    ablation_path = PROJECT_ROOT / "docs" / "results" / "ablation_table.csv"
    if ablation_path.is_file():
        with st.expander("Feature ablation"):
            st.dataframe(load_ablation_table(str(ablation_path)), hide_index=True)
    with st.container(border=True):
        st.markdown("**Known limitations**")
        st.markdown(
            "- Seasonal observations only; this is not a daily forecast.\n"
            "- The model was trained on 2005–2023 data; later-year extrapolation is limited.\n"
            "- The saved prediction range has not been recalibrated for reconstructed neighbor_v3 inputs.\n"
            "- The original historical neighbor generator was not recovered.\n"
            "- The borewell-depth reference is provisional until a supervisor-approved buffer is set."
        )


def render_login(base_url: str):
    st.title("Sign in to groundwater intelligence")
    st.caption("Sign in with an approved account. New users can request access below.")
    status_message = st.session_state.pop("access_status_message", None)
    if status_message:
        st.success(status_message)
    with st.form("login_form", border=True, clear_on_submit=True):
        email = st.text_input("Email", max_chars=254)
        password = st.text_input("Password", type="password", max_chars=128)
        submitted = st.form_submit_button("Sign in", type="primary")
    if submitted:
        try:
            result = request_api(
                "POST", base_url, "/auth/login",
                payload={"email": email.strip(), "password": password}, authenticated=False,
            )
            st.session_state["auth_token"] = result["access_token"]
            st.session_state["auth_user"] = result["user"]
            st.rerun()
        except BackendError as exc:
            st.error(str(exc))

    with st.expander("New user? Request access"):
        st.caption("Verify your email, set a password, then wait for administrator approval before signing in.")
        with st.form("access_request_form", border=True, clear_on_submit=True):
            email = st.text_input("Email", max_chars=254, key="access_request_email")
            submitted = st.form_submit_button("Request access")
        if submitted:
            try:
                result = request_api(
                    "POST", base_url, "/auth/register",
                    payload={"email": email.strip()},
                    authenticated=False,
                )
                st.success(result.get("message", "Check your email for the verification link."))
            except BackendError as exc:
                st.error(str(exc))


def render_complete_registration(base_url: str, token: str):
    st.title("Verify email and set password")
    st.caption("Choose a password of at least 12 characters. An administrator must approve your request before sign-in.")
    with st.form("complete_registration_form", border=True, clear_on_submit=True):
        password = st.text_input("Create password", type="password", max_chars=128)
        confirm = st.text_input("Confirm password", type="password", max_chars=128)
        submitted = st.form_submit_button("Verify email and submit request", type="primary")
    if not submitted:
        return
    if password != confirm:
        st.error("The passwords do not match.")
        return
    try:
        result = request_api(
            "POST", base_url, "/auth/complete-registration",
            payload={"token": token, "password": password},
            authenticated=False,
        )
        message = result.get("message", "Your request is waiting for administrator approval.")
        if not result.get("notification_sent"):
            message += " The administrator will see the request in the app; email alert delivery failed."
        st.session_state["access_status_message"] = message
        st.query_params.clear()
        st.rerun()
    except BackendError as exc:
        st.error(str(exc))


def render_account(user: dict):
    st.header("User account")
    with st.container(border=True):
        st.write(f"**Signed in as:** {user.get('email', '—')}")
        st.write(f"**Role:** {user.get('role', 'user').title()}")
        st.caption("Prediction and station data are served by the project API. Your role controls access to administrative tools.")


def render_admin_panel(base_url: str):
    st.header("Administrator panel")
    try:
        summary = request_api("GET", base_url, "/admin/activity")
        users_result = request_api("GET", base_url, "/admin/users")
        requests_result = request_api("GET", base_url, "/admin/access-requests")
    except BackendError as exc:
        show_api_error(exc)
        return

    first, second, third = st.columns(3)
    first.metric("Accounts", summary.get("users_total", 0))
    second.metric("Active accounts", summary.get("users_active", 0))
    third.metric("Pending access requests", summary.get("pending_access_requests", 0))
    with st.expander("API request totals"):
        st.dataframe(pd.DataFrame(summary.get("api_activity", [])), hide_index=True)

    st.subheader("Access requests")
    access_requests = requests_result.get("requests", [])
    if access_requests:
        st.dataframe(pd.DataFrame(access_requests), hide_index=True)
        choices = {
            f"{item['email']} · requested {item['created_at']}": item
            for item in access_requests
        }
        selected_request = choices[st.selectbox("Select request", list(choices))]
        approve_col, reject_col = st.columns(2)
        if approve_col.button("Approve request", type="primary"):
            try:
                created = request_api(
                    "POST", base_url,
                    f"/admin/access-requests/{selected_request['id']}/approve",
                )
                if created.get("notification_sent"):
                    st.success(f"Approved {created['user']['email']}; an approval email was sent.")
                else:
                    st.warning(f"Approved {created['user']['email']}, but the email could not be sent. Contact them directly.")
                st.rerun()
            except BackendError as exc:
                st.error(str(exc))
        if reject_col.button("Reject request"):
            try:
                result = request_api(
                    "POST", base_url,
                    f"/admin/access-requests/{selected_request['id']}/reject",
                )
                if result.get("notification_sent"):
                    st.success("Access request rejected; an email was sent.")
                else:
                    st.warning("Access request rejected, but the email could not be sent. Contact the requester directly.")
                st.rerun()
            except BackendError as exc:
                st.error(str(exc))
    else:
        st.info("No pending access requests.")

    st.subheader("Create an account")
    with st.form("admin_create_user", border=True, clear_on_submit=True):
        email = st.text_input("New account email", max_chars=254)
        password = st.text_input("Temporary password (12+ characters)", type="password", max_chars=128)
        role = st.selectbox("Role", ["user", "admin"])
        submitted = st.form_submit_button("Create account", type="primary")
    if submitted:
        try:
            created = request_api(
                "POST", base_url, "/admin/users",
                payload={"email": email.strip(), "password": password, "role": role},
            )
            st.success(f"Created {created['user']['role']} account for {created['user']['email']}.")
            st.rerun()
        except BackendError as exc:
            st.error(str(exc))

    st.subheader("Manage accounts")
    users = users_result.get("users", [])
    if users:
        st.dataframe(pd.DataFrame(users), hide_index=True)
        choices = {f"{item['email']} · {item['role']} · {'active' if item['is_active'] else 'disabled'}": item for item in users}
        selected_label = st.selectbox("Select account", list(choices))
        selected = choices[selected_label]
        new_status = st.toggle("Account active", value=bool(selected["is_active"]), key=f"admin_active_{selected['id']}")
        if new_status != bool(selected["is_active"]):
            try:
                request_api(
                    "PATCH", base_url, f"/admin/users/{selected['id']}",
                    payload={"is_active": new_status},
                )
                st.rerun()
            except BackendError as exc:
                st.error(str(exc))
    else:
        st.info("No accounts have been created yet.")


st.set_page_config(page_title="Groundwater intelligence", page_icon="💧", layout="wide")
with st.sidebar:
    st.title("Groundwater intelligence")
    with st.expander("Backend connection", expanded=False):
        api_url = st.text_input("API URL", value=DEFAULT_API_URL).strip().rstrip("/")
try:
    health = get_health(api_url)
except BackendError as exc:
    show_api_error(exc)
    st.stop()

verification_token = st.query_params.get("complete_registration", "")
if verification_token:
    render_complete_registration(api_url, verification_token)
    st.stop()

if st.session_state.get("auth_token"):
    try:
        current_user = request_api("GET", api_url, "/auth/me")
        st.session_state["auth_user"] = current_user
    except BackendError:
        st.session_state.pop("auth_token", None)
        st.session_state.pop("auth_user", None)
        st.warning("Your sign-in expired. Please sign in again.")

if not st.session_state.get("auth_token"):
    render_login(api_url)
    st.stop()

current_user = st.session_state.get("auth_user", {})
with st.sidebar:
    st.caption(f"{current_user.get('email', '')} · {current_user.get('role', 'user').title()}")
    if st.button("Sign out", icon=":material/logout:"):
        try:
            request_api("POST", api_url, "/auth/logout", payload={})
        except BackendError:
            pass
        st.session_state.pop("auth_token", None)
        st.session_state.pop("auth_user", None)
        st.rerun()
    pages = ["Overview", "Stations", "Prediction", "Advisory", "Trends", "Model and data", "My account"]
    if current_user.get("role") == "admin":
        try:
            pending_count = request_api("GET", api_url, "/admin/activity").get(
                "pending_access_requests", 0
            )
        except BackendError:
            pending_count = 0
        if pending_count:
            st.sidebar.warning(
                f"{pending_count} access request(s) need review. Open Administration.",
                icon=":material/notifications_active:",
            )
        pages.append("Administration")
    page = st.radio("View", pages)

st.title("Rajasthan groundwater intelligence")

if health.get("model_loaded") and health.get("database_ready"):
    st.badge(f"Connected · model {health.get('model_version')}", icon=":material/check_circle:", color="green")
else:
    st.badge(f"Backend status · {health.get('status')}", icon=":material/warning:", color="orange")
    if health.get("model_error"):
        st.caption(health["model_error"])

model_info = {}
if page in {"Overview", "Model and data"} and health.get("model_loaded"):
    try:
        model_info = get_json(api_url, "/model/info")
    except BackendError as exc:
        show_api_error(exc)

if page == "Overview":
    render_overview(model_info)
elif page == "Stations":
    render_map(api_url)
elif page == "Prediction":
    render_prediction(api_url, health)
elif page == "Advisory":
    render_advisory(api_url, health)
elif page == "Trends":
    render_trends(api_url)
elif page == "My account":
    render_account(current_user)
elif page == "Administration" and current_user.get("role") == "admin":
    render_admin_panel(api_url)
else:
    if model_info:
        render_model_info(model_info)
    else:
        st.info("Model information is unavailable while the frozen model is not loaded.")
