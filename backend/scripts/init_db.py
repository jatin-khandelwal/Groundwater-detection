from __future__ import annotations

from backend.app.config import DATABASE_PATH
from backend.app.db import initialize_database


if __name__ == "__main__":
    counts = initialize_database(DATABASE_PATH)
    print(f"SQLite database ready: {DATABASE_PATH}")
    for table, count in counts.items():
        print(f"{table}: {count:,} rows")
