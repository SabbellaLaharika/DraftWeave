import os
import unittest
from pathlib import Path
from app.config import settings
from app import database


class TestDatabaseModule(unittest.TestCase):
    def setUp(self):
        # Use a temporary test database
        self.test_db_path = Path("data/test_style_memory.db")
        settings.SQLITE_DB_PATH = str(self.test_db_path)
        database.init_db()

    def tearDown(self):
        if self.test_db_path.exists():
            try:
                os.remove(self.test_db_path)
            except OSError:
                pass

    def test_set_and_get_user_style(self):
        user_id = 123456
        initial_style = database.get_user_style(user_id)
        self.assertIsNone(initial_style)

        custom_style = "Write in the style of a pirate with witty punchlines."
        database.set_user_style(user_id, custom_style)

        retrieved_style = database.get_user_style(user_id)
        self.assertEqual(retrieved_style, custom_style)

    def test_update_user_style(self):
        user_id = 789012
        style_v1 = "Write in formal bullet points."
        style_v2 = "All output must be in the form of a haiku."

        database.set_user_style(user_id, style_v1)
        self.assertEqual(database.get_user_style(user_id), style_v1)

        hash_v1 = database.get_user_style_hash(user_id)

        database.set_user_style(user_id, style_v2)
        self.assertEqual(database.get_user_style(user_id), style_v2)

        hash_v2 = database.get_user_style_hash(user_id)
        self.assertNotEqual(hash_v1, hash_v2)


if __name__ == "__main__":
    unittest.main()
