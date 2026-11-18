from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..services import auth_service
from ..services import email_service


router = APIRouter(tags=["authentication"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class AccessRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class CompleteAccessRequest(BaseModel):
    token: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=12, max_length=128)


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


@router.post("/auth/register", status_code=202)
def register(body: AccessRequest, request: Request):
    if not email_service.is_configured():
        raise HTTPException(503, "Email verification is temporarily unavailable. Contact the administrator.")
    try:
        token = auth_service.request_user_access(request.app.state.db_path, body.email)
    except auth_service.SignupRateLimitError as exc:
        raise HTTPException(429, str(exc), headers={"Retry-After": "3600"}) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if token:
        try:
            email_service.send_verification_email(body.email.strip(), token)
        except email_service.EmailDeliveryError as exc:
            raise HTTPException(503, "Verification email could not be sent. Try again in about a minute.") from exc
    return {
        "status": "received",
        "message": "If this address is eligible, check its inbox for a verification link. Open it to set a password; an administrator reviews the verified request.",
    }


@router.post("/auth/complete-registration")
def complete_registration(body: CompleteAccessRequest, request: Request):
    try:
        verified_email = auth_service.complete_access_registration(
            request.app.state.db_path, body.token, body.password
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not verified_email:
        raise HTTPException(400, "Verification link is invalid, expired, or already used.")
    try:
        email_service.send_admin_request_notice(verified_email)
        notification_sent = True
    except email_service.EmailDeliveryError:
        notification_sent = False
    return {
        "status": "verified",
        "notification_sent": notification_sent,
        "message": "Email verified. Your request is waiting for administrator approval.",
    }


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


@router.get("/admin/access-requests")
def access_requests(request: Request):
    return {"requests": auth_service.list_access_requests(request.app.state.db_path)}


@router.post("/admin/access-requests/{request_id}/approve")
def approve_access_request(request_id: int, request: Request):
    try:
        user = auth_service.approve_access_request(request.app.state.db_path, request_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    notification_sent = True
    try:
        email_service.send_access_decision(user["email"], approved=True)
    except email_service.EmailDeliveryError:
        notification_sent = False
    return {"user": user, "notification_sent": notification_sent}


@router.post("/admin/access-requests/{request_id}/reject")
def reject_access_request(request_id: int, request: Request):
    try:
        email = auth_service.reject_access_request(request.app.state.db_path, request_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    notification_sent = True
    try:
        email_service.send_access_decision(email, approved=False)
    except email_service.EmailDeliveryError:
        notification_sent = False
    return {"status": "rejected", "notification_sent": notification_sent}


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
