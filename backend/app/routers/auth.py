from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..services import auth_service


router = APIRouter(tags=["authentication"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class UserCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    role: str = Field(default="user", pattern="^(user|admin)$")


class UserStatusRequest(BaseModel):
    is_active: bool


@router.post("/auth/login")
def login(body: LoginRequest, request: Request):
    try:
        user, token = auth_service.authenticate(request.app.state.db_path, body.email, body.password)
    except PermissionError as exc:
        raise HTTPException(401, str(exc)) from exc
    return {"access_token": token, "token_type": "bearer", "expires_in": auth_service.SESSION_SECONDS,
            "user": user}


@router.get("/auth/me")
def me(request: Request):
    return request.state.auth_user


@router.post("/auth/logout")
def logout(request: Request):
    auth_service.revoke_session(request.app.state.db_path, request.state.auth_token)
    return {"status": "signed_out"}


@router.get("/admin/users")
def users(request: Request):
    return {"users": auth_service.list_users(request.app.state.db_path)}


@router.post("/admin/users", status_code=201)
def add_user(body: UserCreateRequest, request: Request):
    try:
        user = auth_service.create_user(request.app.state.db_path, body.email, body.password, body.role)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"user": user}


@router.patch("/admin/users/{user_id}")
def update_user(user_id: int, body: UserStatusRequest, request: Request):
    try:
        user = auth_service.set_user_active(
            request.app.state.db_path, user_id, body.is_active, request.state.auth_user["id"]
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"user": user}


@router.get("/admin/activity")
def activity(request: Request):
    return auth_service.activity_summary(request.app.state.db_path)
