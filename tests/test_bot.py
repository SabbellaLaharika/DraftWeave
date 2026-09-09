import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from app.bot.handlers import start_command, setstyle_command, process_content_message
from app import database


class TestBotHandlers(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        database.settings.SQLITE_DB_PATH = "data/test_bot_style_memory.db"
        database.init_db()

    def tearDown(self):
        import os
        from pathlib import Path
        p = Path("data/test_bot_style_memory.db")
        if p.exists():
            try:
                os.remove(p)
            except OSError:
                pass

    async def test_start_command(self):
        update = MagicMock()
        update.message.reply_text = AsyncMock()

        await start_command(update, MagicMock())
        update.message.reply_text.assert_called_once()
        args = update.message.reply_text.call_args[0]
        self.assertIn("Welcome to DraftWeave Content Agent", args[0])

    async def test_setstyle_command_save(self):
        update = MagicMock()
        update.effective_user.id = 999888
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.args = ["Be", "witty", "and", "informal."]

        await setstyle_command(update, context)

        update.message.reply_text.assert_called_once()
        saved_style = database.get_user_style(999888)
        self.assertEqual(saved_style, "Be witty and informal.")

    @patch("app.bot.handlers.sheets_client.is_duplicate")
    @patch("app.bot.handlers.llm_client.generate_content")
    @patch("app.bot.handlers.sheets_client.append_content_row")
    async def test_process_content_message_text(self, mock_append, mock_generate, mock_is_dup):
        mock_is_dup.return_value = False

        dummy_llm = MagicMock()
        dummy_llm.title = "Bot Test Title"
        dummy_llm.category = "Testing"
        dummy_llm.rationale = "Bot test rationale."
        dummy_llm.x_variant = "Short X variant text."
        dummy_llm.linkedin_variant = "LinkedIn variant post text."
        mock_generate.return_value = dummy_llm

        mock_append.return_value = {"appended": True}

        update = MagicMock()
        update.effective_user.id = 111222
        update.message.document = None
        update.message.text = "AI is transforming software engineering."

        status_msg = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=status_msg)

        await process_content_message(update, MagicMock())

        mock_generate.assert_called_once()
        mock_append.assert_called_once()
        status_msg.edit_text.assert_called()


if __name__ == "__main__":
    unittest.main()
