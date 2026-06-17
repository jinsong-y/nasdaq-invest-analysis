from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "update-market-regime-dashboard.yml"


class UpdateMarketRegimeDashboardWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow_text = WORKFLOW.read_text(encoding="utf-8")

    def _run_blocks(self) -> list[str]:
        return re.findall(r"(?ms)^\s*run: \|\n((?:^\s{10}.+\n?)+)", self.workflow_text)

    def _git_add_lines(self) -> list[str]:
        return [
            line.strip()
            for block in self._run_blocks()
            for line in block.splitlines()
            if line.strip().startswith("git add")
        ]

    def test_automatic_publish_workflow_is_public_only_and_github_deployed(self):
        crons = re.findall(r'cron: "([^"]+)"', self.workflow_text)
        self.assertEqual(
            ["0 14 * * 1-5", "0 17 * * 1-5", "30 20 * * 1-5"],
            crons,
        )

        self.assertIn("python scripts/publish_market_regime_dashboard.py", self.workflow_text)
        self.assertNotIn("scripts/update_vercel_dashboard.py", self.workflow_text)

        forbidden_workflow_references = [
            "vercel --prod",
            "vercel deploy",
            "nasdq-analysis.vercel.app",
            "data/raw",
            "data/processed",
            "data/snapshots",
            "docs/DATA_INVENTORY.md",
            "reports/",
            "latest_intraday_inputs",
        ]
        for forbidden in forbidden_workflow_references:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.workflow_text)

        self.assertEqual(["git add -- public"], self._git_add_lines())
        self.assertIn("git diff --cached --quiet", self.workflow_text)
        self.assertIn('json.loads(Path("public/latest.json").read_text', self.workflow_text)
        self.assertIn('git commit -m "chore: publish market regime dashboard ${market_date}"', self.workflow_text)


if __name__ == "__main__":
    unittest.main()
