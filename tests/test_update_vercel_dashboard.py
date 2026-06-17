from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import update_vercel_dashboard


class DeprecatedUpdateEntrypointTests(unittest.TestCase):
    def test_run_update_delegates_to_automatic_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(update_vercel_dashboard, "run_automatic_publish", return_value=True) as publish:
                result = update_vercel_dashboard.run_update(root, fetch=True)

            self.assertTrue(result)
            publish.assert_called_once_with(root, fetch=True)

    def test_run_update_rejects_intraday_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(update_vercel_dashboard, "run_automatic_publish") as publish:
                with self.assertRaisesRegex(RuntimeError, "intraday overlay is not part"):
                    update_vercel_dashboard.run_update(root, fetch=True, fetch_intraday=True)

            publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
