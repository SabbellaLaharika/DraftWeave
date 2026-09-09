import sys
import logging
from app.config import settings
from app.database import init_db
from app.bot import create_telegram_application

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("DraftWeave")


def main() -> None:
    logger.info("Initializing DraftWeave Agent Service...")

    # Step 1: Initialize SQLite Style Memory Database
    init_db()
    logger.info(f"SQLite Style Memory DB initialized at: {settings.SQLITE_DB_PATH}")

    # Step 2: Build Telegram Application and start Long Polling
    logger.info("Starting Telegram Bot via Long Polling...")
    app = create_telegram_application()
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
