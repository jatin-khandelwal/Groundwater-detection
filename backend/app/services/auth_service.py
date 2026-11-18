from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
from typing import Any

from ..db import connect


PASSWORD_ITERATIONS = 310_000
SESSION_SECONDS = 12 * 60 * 60
MAX_LOGIN_FAILURES = 5
LOCK_SECONDS = 15 * 60
VERIFICATION_SECONDS = 24 * 60 * 60
SIGNUP_WINDOW_SECONDS = 60 * 60
SIGNUP_EMAIL_LIMIT = 3
SIGNUP_GLOBAL_LIMIT = 30
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class SignupRateLimitError(ValueError):
    pass


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def validate_credentials(email: str, password: str) -> None:
    if not EMAIL_RE.fullmatch(email.strip()) or len(email) > 254:
        raise ValueError("Enter a valid email address.")
    if len(password) < 12 or len(password) > 128:
        raise ValueError("Password must be between 12 and 128 characters.")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_user(db_path, email: str, password: str, role: str = "user") -> dict[str, Any]:
    validate_credentials(email, password)
    email = normalize_email(email)
    if role not in {"user", "admin"}:
        raise ValueError("Role must be user or admin.")
    with connect(db_path) as conn:
        try:
            cur = conn.execute(
                "INSERT INTO auth_users(email,password_hash,role) VALUES(?,?,?)",
                (email, hash_password(password), role),
            )
            conn.commit()
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise ValueError("An account with this email already exists.") from exc
            raise
        row = conn.execute(
            "SELECT id,email,role,is_active,created_at FROM auth_users WHERE id=?", (cur.lastrowid,)
        ).fetchone()
    return dict(row)


def _check_signup_rate_limits(conn, email: str, now: int) -> None:
    conn.execute(
        "DELETE FROM auth_signup_rate_limits WHERE window_started_at < ?",
        (now - SIGNUP_WINDOW_SECONDS,),
    )
    keys = {
        "global": ("all", SIGNUP_GLOBAL_LIMIT),
        "email": (hashlib.sha256(email.encode("utf-8")).hexdigest(), SIGNUP_EMAIL_LIMIT),
    }
    current = {}
    for scope, (key_hash, limit) in keys.items():
        row = conn.execute(
            "SELECT window_started_at,attempts FROM auth_signup_rate_limits "
            "WHERE scope=? AND key_hash=?",
            (scope, key_hash),
        ).fetchone()
        attempts = row["attempts"] if row and now - row["window_started_at"] < SIGNUP_WINDOW_SECONDS else 0
        if attempts >= limit:
            raise SignupRateLimitError("Too many access requests. Please try again later.")
        current[scope] = (key_hash, attempts, limit)

    for scope, (key_hash, attempts, _) in current.items():
        if attempts:
            conn.execute(
                "UPDATE auth_signup_rate_limits SET attempts=attempts+1 "
                "WHERE scope=? AND key_hash=?",
                (scope, key_hash),
            )
        else:
            conn.execute(
                "INSERT INTO auth_signup_rate_limits(scope,key_hash,window_started_at,attempts) "
                "VALUES(?,?,?,1) ON CONFLICT(scope,key_hash) DO UPDATE SET "
                "window_started_at=excluded.window_started_at,attempts=1",
                (scope, key_hash, now),
            )


def request_user_access(db_path, email: str) -> str | None:
    if not EMAIL_RE.fullmatch(email.strip()) or len(email) > 254:
        raise ValueError("Enter a valid email address.")
    email = normalize_email(email)
    now = int(time.time())
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    with connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _check_signup_rate_limits(conn, email, now)
        conn.execute(
            "DELETE FROM auth_requests WHERE status='pending' "
            "AND created_at < datetime('now','-30 days')"
        )
        existing_user = conn.execute(
            "SELECT 1 FROM auth_users WHERE email=? COLLATE NOCASE", (email,)
        ).fetchone()
        if existing_user:
            conn.commit()
            return

        existing_request = conn.execute(
            "SELECT status,email_verified,verification_expires_at,last_verification_sent_at "
            "FROM auth_requests WHERE email=? COLLATE NOCASE",
            (email,),
        ).fetchone()
        if existing_request and existing_request["status"] == "pending" and existing_request["email_verified"]:
            conn.commit()
            return

        if (
            existing_request
            and existing_request["status"] == "pending"
            and existing_request["last_verification_sent_at"]
            and now - existing_request["last_verification_sent_at"] < 60
            and existing_request["verification_expires_at"]
            and existing_request["verification_expires_at"] > now
        ):
            conn.commit()
            return

        expires_at = now + VERIFICATION_SECONDS
        if existing_request:
            conn.execute(
                "UPDATE auth_requests SET password_hash=NULL,status='pending',email_verified=0,"
                "verification_token_hash=?,verification_expires_at=?,last_verification_sent_at=?,"
                "created_at=CURRENT_TIMESTAMP,reviewed_at=NULL WHERE email=? COLLATE NOCASE",
                (token_hash, expires_at, now, email),
            )
        else:
            conn.execute(
                "INSERT INTO auth_requests(email,password_hash,verification_token_hash,"
                "verification_expires_at,last_verification_sent_at) VALUES(?,?,?,?,?)",
                (email, None, token_hash, expires_at, now),
            )
        conn.commit()
    return token


def complete_access_registration(db_path, token: str, password: str) -> str | None:
    if not token or len(token) > 128:
        return None
    token_hash = hashlib.sha256(token.encode("ascii", errors="ignore")).hexdigest()
    now = int(time.time())
    with connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id,email FROM auth_requests WHERE status='pending' AND email_verified=0 "
            "AND verification_token_hash=? AND verification_expires_at>?",
            (token_hash, now),
        ).fetchone()
        if not row:
            return None
        validate_credentials(row["email"], password)
        password_hash = hash_password(password)
        conn.execute(
            "UPDATE auth_requests SET password_hash=?,email_verified=1,verification_token_hash=NULL,"
            "verification_expires_at=NULL WHERE id=?",
            (password_hash, row["id"]),
        )
        conn.commit()
    return row["email"]


def list_access_requests(db_path) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        conn.execute(
            "DELETE FROM auth_requests WHERE status='pending' "
            "AND created_at < datetime('now','-30 days')"
        )
        conn.commit()
        rows = conn.execute(
            "SELECT id,email,created_at FROM auth_requests WHERE status='pending' AND email_verified=1 "
            "ORDER BY created_at,id"
        ).fetchall()
    return [dict(row) for row in rows]


def approve_access_request(db_path, request_id: int) -> dict[str, Any]:
    with connect(db_path) as conn:
        request = conn.execute(
            "SELECT email,password_hash,status,email_verified FROM auth_requests WHERE id=?", (request_id,)
        ).fetchone()
        if not request:
            raise LookupError("Access request not found.")
        if request["status"] != "pending" or not request["email_verified"] or not request["password_hash"]:
            raise ValueError("This access request is no longer pending.")
        try:
            cursor = conn.execute(
                "INSERT INTO auth_users(email,password_hash,role,is_active) VALUES(?,?,'user',1)",
                (request["email"], request["password_hash"]),
            )
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise ValueError("An account with this email already exists.") from exc
            raise
        conn.execute(
            "UPDATE auth_requests SET password_hash=NULL,status='approved',reviewed_at=CURRENT_TIMESTAMP "
            "WHERE id=?",
            (request_id,),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id,email,role,is_active,created_at FROM auth_users WHERE id=?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


def reject_access_request(db_path, request_id: int) -> str:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT email FROM auth_requests WHERE id=? AND status='pending' AND email_verified=1",
            (request_id,),
        ).fetchone()
        if not row:
            exists = conn.execute("SELECT 1 FROM auth_requests WHERE id=?", (request_id,)).fetchone()
            if not exists:
                raise LookupError("Access request not found.")
            raise ValueError("This access request is no longer pending.")
        conn.execute(
            "UPDATE auth_requests SET password_hash=NULL,status='rejected',reviewed_at=CURRENT_TIMESTAMP "
            "WHERE id=? AND status='pending' AND email_verified=1",
            (request_id,),
        )
        conn.commit()
    return row["email"]


def reset_password(db_path, email: str, password: str) -> dict[str, Any]:
    validate_credentials(email, password)
    email = normalize_email(email)
    with connect(db_path) as conn:
        row = conn.execute("SELECT id,email,role FROM auth_users WHERE email=? COLLATE NOCASE", (email,)).fetchone()
        if not row:
            raise LookupError("No account exists for that email.")
        conn.execute("UPDATE auth_users SET password_hash=? WHERE id=?", (hash_password(password), row["id"]))
        conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (row["id"],))
        conn.execute("DELETE FROM auth_login_attempts WHERE email=?", (email,))
        conn.commit()
    return {"id": row["id"], "email": row["email"], "role": row["role"]}


def authenticate(db_path, email: str, password: str) -> tuple[dict[str, Any], str]:
    email = normalize_email(email)
    now = int(time.time())
    with connect(db_path) as conn:
        attempt = conn.execute(
            "SELECT failed_attempts,locked_until FROM auth_login_attempts WHERE email=?", (email,)
        ).fetchone()
        if attempt and attempt["locked_until"] > now:
            raise PermissionError("Invalid email or password, or sign-in is temporarily locked.")
        row = conn.execute(
            "SELECT id,email,password_hash,role,is_active FROM auth_users WHERE email=? COLLATE NOCASE",
            (email,),
        ).fetchone()

        dummy = "pbkdf2_sha256$310000$MDEyMzQ1Njc4OWFiY2RlZg==$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        correct = verify_password(password, row["password_hash"] if row else dummy)
        if not row or not correct or not row["is_active"]:
            failures = (attempt["failed_attempts"] if attempt else 0) + 1
            locked_until = now + LOCK_SECONDS if failures >= MAX_LOGIN_FAILURES else 0
            conn.execute(
                "INSERT INTO auth_login_attempts(email,failed_attempts,locked_until) VALUES(?,?,?) "
                "ON CONFLICT(email) DO UPDATE SET failed_attempts=excluded.failed_attempts,locked_until=excluded.locked_until",
                (email, failures, locked_until),
            )
            conn.commit()
            raise PermissionError("Invalid email or password, or sign-in is temporarily locked.")

        conn.execute("DELETE FROM auth_login_attempts WHERE email=?", (email,))
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        conn.execute(
            "INSERT INTO auth_sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
            (token_hash, row["id"], now + SESSION_SECONDS),
        )
        conn.commit()
    return {"id": row["id"], "email": row["email"], "role": row["role"]}, token


def session_user(db_path, token: str) -> dict[str, Any] | None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = int(time.time())
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT u.id,u.email,u.role,u.is_active,s.expires_at FROM auth_sessions s "
            "JOIN auth_users u ON u.id=s.user_id WHERE s.token_hash=?", (token_hash,),
        ).fetchone()
        if not row or not row["is_active"] or row["expires_at"] <= now:
            conn.execute("DELETE FROM auth_sessions WHERE token_hash=?", (token_hash,))
            conn.commit()
            return None
    return {"id": row["id"], "email": row["email"], "role": row["role"]}


def revoke_session(db_path, token: str) -> None:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with connect(db_path) as conn:
        conn.execute("DELETE FROM auth_sessions WHERE token_hash=?", (token_hash,))
        conn.commit()


def list_users(db_path) -> list[dict[str, Any]]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id,email,role,is_active,created_at FROM auth_users ORDER BY created_at DESC,id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def set_user_active(db_path, user_id: int, active: bool, actor_id: int) -> dict[str, Any]:
    with connect(db_path) as conn:
        row = conn.execute("SELECT id,email,role,is_active FROM auth_users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise LookupError("Account not found.")
        if user_id == actor_id and not active:
            raise ValueError("You cannot deactivate your own account.")
        if row["role"] == "admin" and row["is_active"] and not active:
            active_admins = conn.execute(
                "SELECT COUNT(*) FROM auth_users WHERE role='admin' AND is_active=1"
            ).fetchone()[0]
            if active_admins <= 1:
                raise ValueError("The last active admin cannot be deactivated.")
        conn.execute("UPDATE auth_users SET is_active=? WHERE id=?", (int(active), user_id))
        if not active:
            conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (user_id,))
        conn.commit()
        return {"id": row["id"], "email": row["email"], "role": row["role"], "is_active": bool(active)}


def activity_summary(db_path) -> dict[str, Any]:
    with connect(db_path) as conn:
        users = conn.execute("SELECT COUNT(*) FROM auth_users").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM auth_users WHERE is_active=1").fetchone()[0]
        pending_requests = conn.execute(
            "SELECT COUNT(*) FROM auth_requests WHERE status='pending' AND email_verified=1"
        ).fetchone()[0]
        events = conn.execute(
            "SELECT endpoint,COUNT(*) AS requests,MAX(created_at) AS last_request "
            "FROM prediction_log GROUP BY endpoint ORDER BY endpoint"
        ).fetchall()
    return {
        "users_total": users,
        "users_active": active,
        "pending_access_requests": pending_requests,
        "api_activity": [dict(row) for row in events],
    }
