import unittest
from app import database
from app.healthcheck import check_health


class TestHealthCheck(unittest.TestCase):
    def setUp(self):
        database.settings.SQLITE_DB_PATH = "data/test_health_memory.db"
        database.init_db()

    def tearDown(self):
        import os
        from pathlib import Path
        p = Path("data/test_health_memory.db")
        if p.exists():
            try:
                os.remove(p)
            except OSError:
                pass

    def test_check_health_success(self):
        self.assertTrue(check_health())


if __name__ == "__main__":
    unittest.main()
