import sys
import logging
from app.config import settings
from app.database import get_db_connection

logging.basicConfig(level=logging.ERROR)


def check_health() -> bool:
    """
    Verify application health:
    1. Check SQLite database connection and table integrity.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_styles'")
        row = cursor.fetchone()
        conn.close()
        if not row:
            sys.exit(1)
        return True
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    if check_health():
        sys.exit(0)
    else:
        sys.exit(1)
