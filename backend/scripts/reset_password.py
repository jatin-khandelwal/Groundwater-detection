from __future__ import annotations

import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.config import DATABASE_PATH
from backend.app.services.auth_service import reset_password


def main() -> None:
    email = input("Account email to reset: ").strip()
    password = getpass.getpass("New password (12+ characters): ")
    confirm = getpass.getpass("Confirm new password: ")
    if password != confirm:
        raise SystemExit("Passwords did not match.")
    try:
        user = reset_password(DATABASE_PATH, email, password)
    except (LookupError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Password reset for {user['email']}. Existing sessions were signed out.")


if __name__ == "__main__":
    main()
