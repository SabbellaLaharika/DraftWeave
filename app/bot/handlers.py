import logging
from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from app.database import set_user_style, get_user_style, delete_user_style, get_user_style_hash
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
        "• /setstyle <style description> - Save your house style (e.g. `/setstyle Be witty and use bullet points`)\n"
        "• /showstyle - View your active style preference\n"
        "• /resetstyle - Reset your style to default standard style\n"
        "• /start - Show this welcome message."
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


async def showstyle_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /showstyle command. Displays current user style prompt.
    """
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id
    current_style = get_user_style(user_id)

    if current_style:
        msg = f"🎨 **Your Current Active House Style:**\n\n\"{current_style}\"\n\nTo change it, use `/setstyle <new description>`. To reset, use `/resetstyle`."
    else:
        msg = "ℹ️ **No custom style currently set.**\nUsing standard default editorial persona. Use `/setstyle <description>` to define your house style."

    await update.message.reply_text(msg, parse_mode="Markdown")


async def resetstyle_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /resetstyle command. Clears user style preference back to default.
    """
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id
    delete_user_style(user_id)

    msg = "✅ **Style preference reset!**\nYour persona has been restored to standard default editorial style."
    await update.message.reply_text(msg, parse_mode="Markdown")


async def safe_edit_status(msg, text: str, parse_mode: Optional[str] = None, reply_markup=None) -> None:
    """Safely edit Telegram status message with automatic plain-text fallback if Markdown parsing fails."""
    if not msg:
        return
    try:
        await msg.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as err:
        logger.warning(f"Status edit failed with parse_mode='{parse_mode}': {err}. Retrying in plain text fallback...")
        try:
            # Strip simple markdown syntax for clean plain-text fallback
            plain_text = text.replace("**", "").replace("`", "").replace("*", "")
            await msg.edit_text(plain_text, parse_mode=None, reply_markup=reply_markup)
        except Exception as fallback_err:
            logger.error(f"Failed to edit status message in plain text fallback: {fallback_err}")


async def safe_reply_text(message_or_query, text: str, parse_mode: Optional[str] = "Markdown", reply_markup=None) -> None:
    """Safely reply to a message with automatic plain-text fallback if Markdown parsing fails."""
    try:
        await message_or_query.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as err:
        logger.warning(f"Reply failed with parse_mode='{parse_mode}': {err}. Retrying in plain text fallback...")
        plain_text = text.replace("**", "").replace("`", "").replace("*", "")
        try:
            await message_or_query.reply_text(plain_text, parse_mode=None, reply_markup=reply_markup)
        except Exception as fallback_err:
            logger.error(f"Failed to reply in plain text fallback: {fallback_err}")


async def process_content_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle incoming text messages (plain text or URL) and PDF document attachments.
    """
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id
    status_msg = None
    try:
        status_msg = await update.message.reply_text("⏳ Processing your content...")
    except Exception as e:
        logger.warning(f"Failed to send initial status message: {e}")

    try:
        # Determine input type: Document (PDF) vs Text/URL
        if update.message.document:
            document = update.message.document
            filename = document.file_name or "document.pdf"
            mime_type = document.mime_type or ""

            if not (mime_type == "application/pdf" or filename.lower().endswith(".pdf")):
                await safe_edit_status(status_msg, "⚠️ Unsupported document type. Please upload a PDF file.")
                return

            await safe_edit_status(status_msg, "📥 Downloading PDF document...")
            file_obj = await context.bot.get_file(document.file_id)
            pdf_bytes = await file_obj.download_as_bytearray()

            await safe_edit_status(status_msg, "⚙️ Extracting PDF layout with MarkItDown...")
            extracted = extract_content(bytes(pdf_bytes), filename=filename)

        elif update.message.text:
            text_content = update.message.text.strip()
            if text_content.startswith("/"):
                return  # Skip unknown command execution

            await safe_edit_status(status_msg, "⚙️ Extracting content...")
            extracted = extract_content(text_content)
        else:
            await safe_edit_status(status_msg, "⚠️ Unsupported message format. Send text, a URL, or a PDF attachment.")
            return

        # Fetch stored user style preference
        user_style = get_user_style(user_id)
        style_hash = get_user_style_hash(user_id) if user_style else None

        # Check Google Sheets idempotency
        await safe_edit_status(status_msg, "🔍 Checking duplicate entries in Google Sheets...")
        if sheets_client.is_duplicate(extracted.source_identifier, style_hash=style_hash, user_id=user_id):
            cached_result = sheets_client.find_cached_llm_result(extracted.source_identifier, style_hash=style_hash)
            if cached_result:
                msg_id_str = str(update.message.message_id)
                context.user_data[f"x_{msg_id_str}"] = cached_result.x_variant
                context.user_data[f"li_{msg_id_str}"] = cached_result.linkedin_variant

                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("📱 Copy X Draft", callback_data=f"copy_x_{msg_id_str}"),
                        InlineKeyboardButton("💼 Copy LinkedIn Draft", callback_data=f"copy_li_{msg_id_str}")
                    ]
                ])

                response_summary = (
                    f"ℹ️ **Duplicate Detected (Retrieved from Google Sheets)**\n"
                    f"_Logged previously under your current style settings. Use `/setstyle` to re-generate with a new style._\n\n"
                    f"📌 **Title:** {cached_result.title}\n"
                    f"🏷️ **Category:** `{cached_result.category}`\n"
                    f"💡 **Rationale:** {cached_result.rationale}\n\n"
                    f"📱 **X Variant ({len(cached_result.x_variant)} chars):**\n{cached_result.x_variant}\n\n"
                    f"💼 **LinkedIn Variant:**\n{cached_result.linkedin_variant}\n\n"
                    f"⚡ *Retrieved from Google Sheet (ContentType '{extracted.content_type}')*"
                )
                await safe_edit_status(status_msg, response_summary, parse_mode="Markdown", reply_markup=keyboard)
            else:
                await safe_edit_status(
                    status_msg,
                    "ℹ️ **Duplicate Detected**: This content has already been logged to your Google Sheet "
                    "under your current style settings. (Use `/setstyle` if you wish to re-generate with a new style)."
                )
            return

        # Call LLM orchestrator
        await safe_edit_status(status_msg, "🤖 Generating social media drafts with LLM...")
        llm_result = llm_client.generate_content(extracted.raw_text, style_prompt=user_style)

        # Log row to Google Sheets
        await safe_edit_status(status_msg, "📊 Saving entry to Google Sheets...")
        append_res = sheets_client.append_content_row(
            source_identifier=extracted.source_identifier,
            content_type=extracted.content_type,
            llm_result=llm_result,
            style_hash=style_hash,
            user_id=user_id
        )

        # Store drafts in context.user_data for quick 1-tap copying
        msg_id_str = str(update.message.message_id)
        context.user_data[f"x_{msg_id_str}"] = llm_result.x_variant
        context.user_data[f"li_{msg_id_str}"] = llm_result.linkedin_variant

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📱 Copy X Draft", callback_data=f"copy_x_{msg_id_str}"),
                InlineKeyboardButton("💼 Copy LinkedIn Draft", callback_data=f"copy_li_{msg_id_str}")
            ]
        ])

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
        if status_msg:
            await safe_edit_status(status_msg, response_summary, parse_mode="Markdown", reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error processing content message for user {user_id}: {e}", exc_info=True)
        await safe_edit_status(status_msg, f"❌ **Error processing content:**\n`{str(e)}`", parse_mode="Markdown")


async def draft_copy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle inline keyboard button clicks for 1-tap draft copying.
    """
    query = update.callback_query
    if not query:
        return

    await query.answer()
    data = query.data or ""

    if data.startswith("copy_x_"):
        msg_id_str = data.replace("copy_x_", "")
        draft = context.user_data.get(f"x_{msg_id_str}")
        if draft:
            await safe_reply_text(query.message, f"📱 **X Post (Tap block below to copy):**\n\n```\n{draft}\n```", parse_mode="Markdown")
        else:
            await query.message.reply_text("⚠️ Draft unavailable or session expired.")

    elif data.startswith("copy_li_"):
        msg_id_str = data.replace("copy_li_", "")
        draft = context.user_data.get(f"li_{msg_id_str}")
        if draft:
            await safe_reply_text(query.message, f"💼 **LinkedIn Post (Tap block below to copy):**\n\n```\n{draft}\n```", parse_mode="Markdown")
        else:
            await query.message.reply_text("⚠️ Draft unavailable or session expired.")
