import logging
from telegram import BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from app.config import settings
from app.bot.handlers import (
    start_command,
    setstyle_command,
    showstyle_command,
    resetstyle_command,
    process_content_message,
    draft_copy_callback
)

logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """Register bot commands in Telegram's native Menu popup."""
    bot_commands = [
        BotCommand("start", "Show welcome message & usage guide"),
        BotCommand("setstyle", "Set custom house style (e.g. /setstyle Be witty)"),
        BotCommand("showstyle", "View active house style preference"),
        BotCommand("resetstyle", "Reset style to default standard persona")
    ]
    try:
        await application.bot.set_my_commands(bot_commands)
        logger.info("Successfully registered Telegram bot commands menu.")
    except Exception as err:
        logger.warning(f"Failed to set bot commands menu: {err}")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors caused by updates gracefully."""
    logger.warning(f"Telegram API Update exception caught: {context.error}")


def create_telegram_application() -> Application:
    """
    Build and configure python-telegram-bot Application.
    """
    token = settings.TELEGRAM_BOT_TOKEN
    if not token or token == "your_telegram_bot_token_here":
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is missing or unconfigured.")

    builder = ApplicationBuilder().token(token).post_init(post_init)
    app = builder.build()

    # Command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("setstyle", setstyle_command))
    app.add_handler(CommandHandler("showstyle", showstyle_command))
    app.add_handler(CommandHandler("resetstyle", resetstyle_command))

    # Inline button callback handler
    app.add_handler(CallbackQueryHandler(draft_copy_callback))

    # Content ingestion message handlers (Text, URLs, and Documents/PDFs)
    content_filter = (filters.TEXT & ~filters.COMMAND) | filters.Document.ALL
    app.add_handler(MessageHandler(content_filter, process_content_message))

    # Global error handler
    app.add_error_handler(error_handler)

    return app
