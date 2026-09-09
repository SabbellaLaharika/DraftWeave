import logging
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters
)
from app.config import settings
from app.bot.handlers import (
    start_command,
    setstyle_command,
    process_content_message
)

logger = logging.getLogger(__name__)


def create_telegram_application() -> Application:
    """
    Build and configure python-telegram-bot Application.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    if not token or token == "your_telegram_bot_token_here":
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is missing or unconfigured.")

    builder = ApplicationBuilder().token(token)
    app = builder.build()

    # Command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("setstyle", setstyle_command))

    # Content ingestion message handlers (Text, URLs, and Documents/PDFs)
    content_filter = (filters.TEXT & ~filters.COMMAND) | filters.Document.ALL
    app.add_handler(MessageHandler(content_filter, process_content_message))

    return app
