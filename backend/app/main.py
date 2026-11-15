from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import AUTO_INIT_DB, CORS_ORIGINS, DATABASE_PATH
from .db import database_exists, ensure_runtime_schema, initialize_database
from .routers import advisory, auth, history, locations, meta, predict
from .services.auth_service import session_user
from .services.model_service import ModelService


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_path = DATABASE_PATH
    app.state.database_ready = database_exists(DATABASE_PATH)
    if not app.state.database_ready and AUTO_INIT_DB:
        try:
            initialize_database(DATABASE_PATH)
            app.state.database_ready = database_exists(DATABASE_PATH)
        except Exception as exc:
            app.state.database_error = f"{type(exc).__name__}: {exc}"
    if app.state.database_ready:
        ensure_runtime_schema(DATABASE_PATH)
    model = ModelService()
    model.load()
    app.state.model_service = model
    yield


app = FastAPI(
    title="Groundwater Intelligence API",
    description=(
        "Demo 2 seasonal groundwater-level prediction and borewell advisory API. "
        "Water level is depth to water; larger values mean water is deeper below ground."
    ),
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_session(request: Request, call_next):
    path = request.url.path
    public_paths = {"/health", "/auth/login", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
    if request.method == "OPTIONS" or path in public_paths:
        return await call_next(request)

    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.casefold() != "bearer" or not token:
        return JSONResponse({"detail": "Sign-in required."}, status_code=401)

    db_path = getattr(request.app.state, "db_path", DATABASE_PATH)
    user = session_user(db_path, token)
    if user is None:
        return JSONResponse({"detail": "Session expired or invalid. Sign in again."}, status_code=401)
    if path.startswith("/admin") and user["role"] != "admin":
        return JSONResponse({"detail": "Administrator access required."}, status_code=403)

    request.state.auth_user = user
    request.state.auth_token = token
    return await call_next(request)


app.include_router(meta.router)
app.include_router(locations.router)
app.include_router(history.router)
app.include_router(predict.router)
app.include_router(advisory.router)
app.include_router(auth.router)
