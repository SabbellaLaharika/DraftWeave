import logging
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from app.database import set_user_style, get_user_style, get_user_style_hash
from app.extractors import extract_content
from app.llm import llm_client
from app.sheets import sheets_client

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /start command. Replies with welcome message and bot usage instructions.
    """
    welcome_text = (
        "🤖 **Welcome to DraftWeave Content Agent!**\n\n"
        "I am your multi-format content curator and strategist. Send me:\n"
        "1. 📝 **Plain Text**: A thought, snippet, or notes.\n"
        "2. 🔗 **Web Link**: A news article or blog post URL.\n"
        "3. 📄 **PDF Document**: A whitepaper, report, or guide.\n\n"
        "I will extract the content, apply your persona style, generate optimized X & LinkedIn drafts using LLMs, "
        "and log everything into your Google Sheet.\n\n"
        "⚙️ **Commands:**\n"
        "• `/setstyle <style description>` - Save your house style (e.g. `/setstyle Be witty and use bullet points`)\n"
        "• `/start` - Show this welcome message."
    )
    if update.message:
        await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def setstyle_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /setstyle command. Saves persistent user style preference to SQLite.
    """
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id

    if not context.args:
        current_style = get_user_style(user_id)
        if current_style:
            msg = f"Your current style setting is:\n\n\"{current_style}\"\n\nTo update, run `/setstyle <new style description>`."
        else:
            msg = "Please specify a style prompt after the command.\nExample: `/setstyle Write in the style of a witty tech analyst with punchy bullet points.`"
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    style_prompt = " ".join(context.args).strip()
    set_user_style(user_id, style_prompt)

    response_text = (
        "✅ **Style preference saved!**\n\n"
        f"Your style guide has been updated to:\n\"{style_prompt}\"\n\n"
        "All future content generations will incorporate this style preference."
    )
    await update.message.reply_text(response_text, parse_mode="Markdown")


async def process_content_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle incoming text messages (plain text or URL) and PDF document attachments.
    """
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id
    status_msg = await update.message.reply_text("⏳ Processing your content...")

    try:
        # Determine input type: Document (PDF) vs Text/URL
        if update.message.document:
            document = update.message.document
            filename = document.file_name or "document.pdf"
            mime_type = document.mime_type or ""

            if not (mime_type == "application/pdf" or filename.lower().endswith(".pdf")):
                await status_msg.edit_text("⚠️ Unsupported document type. Please upload a PDF file.")
                return

            await status_msg.edit_text("📥 Downloading PDF document...")
            file_obj = await context.bot.get_file(document.file_id)
            pdf_bytes = await file_obj.download_as_bytearray()

            await status_msg.edit_text("⚙️ Extracting PDF layout with MarkItDown...")
            extracted = extract_content(bytes(pdf_bytes), filename=filename)

        elif update.message.text:
            text_content = update.message.text.strip()
            if text_content.startswith("/"):
                return  # Skip unknown command execution

            await status_msg.edit_text("⚙️ Extracting content...")
            extracted = extract_content(text_content)
        else:
            await status_msg.edit_text("⚠️ Unsupported message format. Send text, a URL, or a PDF attachment.")
            return

        # Fetch stored user style preference
        user_style = get_user_style(user_id)
        style_hash = get_user_style_hash(user_id) if user_style else None

        # Check Google Sheets idempotency
        await status_msg.edit_text("🔍 Checking duplicate entries in Google Sheets...")
        if sheets_client.is_duplicate(extracted.source_identifier, style_hash=style_hash):
            await status_msg.edit_text(
                "ℹ️ **Duplicate Detected**: This content has already been logged to your Google Sheet "
                "under your current style settings. (Use `/setstyle` if you wish to re-generate with a new style)."
            )
            return

        # Call LLM orchestrator
        await status_msg.edit_text("🤖 Generating social media drafts with LLM...")
        llm_result = llm_client.generate_content(extracted.raw_text, style_prompt=user_style)

        # Log row to Google Sheets
        await status_msg.edit_text("📊 Saving entry to Google Sheets...")
        append_res = sheets_client.append_content_row(
            source_identifier=extracted.source_identifier,
            content_type=extracted.content_type,
            llm_result=llm_result,
            style_hash=style_hash
        )

        # Format final Telegram response
        response_summary = (
            f"🎉 **Content Processed & Logged!**\n\n"
            f"📌 **Title:** {llm_result.title}\n"
            f"🏷️ **Category:** `{llm_result.category}`\n"
            f"💡 **Rationale:** {llm_result.rationale}\n\n"
            f"📱 **X Variant ({len(llm_result.x_variant)} chars):**\n{llm_result.x_variant}\n\n"
            f"💼 **LinkedIn Variant:**\n{llm_result.linkedin_variant}\n\n"
            f"✅ *Saved to Google Sheet under ContentType '{extracted.content_type}'*"
        )
        await status_msg.edit_text(response_summary, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error processing content message for user {user_id}: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ **Error processing content:**\n`{str(e)}`", parse_mode="Markdown")
