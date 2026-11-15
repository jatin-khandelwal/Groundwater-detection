from __future__ import annotations

import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.config import DATABASE_PATH
from backend.app.db import ensure_runtime_schema, initialize_database, database_exists
from backend.app.services.auth_service import create_user


def main() -> None:
    if not database_exists(DATABASE_PATH):
        initialize_database(DATABASE_PATH)
    ensure_runtime_schema(DATABASE_PATH)
    email = input("Admin email: ").strip()
    password = getpass.getpass("Admin password (12+ characters): ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords did not match.")
    try:
        user = create_user(DATABASE_PATH, email, password, "admin")
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Admin account created: {user['email']}")


if __name__ == "__main__":
    main()
