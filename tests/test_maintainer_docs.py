from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
PROJECT_STRUCTURE = ROOT / "docs" / "PROJECT_STRUCTURE.md"
ADR_0001 = ROOT / "docs" / "adr" / "0001-public-only-automatic-publish.md"


class MaintainerDocsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.readme = README.read_text(encoding="utf-8")
        self.project_structure = PROJECT_STRUCTURE.read_text(encoding="utf-8")
        self.adr = ADR_0001.read_text(encoding="utf-8")
        self.docs = {
            "README.md": self.readme,
            "docs/PROJECT_STRUCTURE.md": self.project_structure,
        }
        self.maintainer_docs = "\n\n".join([self.readme, self.project_structure, self.adr])

    def test_maintainer_docs_use_public_only_automatic_publish_language(self):
        for term in [
            "Market Regime Dashboard",
            "Research Report",
            "Automatic Publish",
            "Daily Input",
            "Publishable Market Date",
            "Stale Dashboard",
            "Published Artifact",
        ]:
            with self.subTest(term=term):
                self.assertIn(term, self.maintainer_docs)

        for path, text in self.docs.items():
            with self.subTest(path=path):
                self.assertIn(
                    "Automatic Publish is the recurring release of the Market Regime Dashboard",
                    text,
                )
                self.assertIn("python scripts/publish_market_regime_dashboard.py", text)
                self.assertNotIn("python scripts/publish_market_regime_dashboard.py --fetch", text)

    def test_maintainer_docs_describe_public_only_commit_scope(self):
        for path, text in self.docs.items():
            with self.subTest(path=path):
                self.assertIn(
                    "Automatic Publish commits only Published Artifacts under `public/`",
                    text,
                )
                self.assertIn(
                    "Raw data, snapshots, processed data, and Research Reports are not committed by Automatic Publish",
                    text,
                )
                self.assertIn("Research Reports remain manual/offline artifacts", text)

    def test_maintainer_docs_keep_github_driven_vercel_deployment(self):
        self.assertIn("GitHub-driven", self.maintainer_docs)
        self.assertIn("Vercel auto-deploy", self.maintainer_docs)
        self.assertIn("https://nasdaq-invest-analysis.vercel.app", self.maintainer_docs)

        forbidden = [
            "vercel --prod",
            "vercel deploy",
            "nasdq-analysis.vercel.app",
            "reconnect",
            "recreate",
        ]
        for text in forbidden:
            with self.subTest(text=text):
                self.assertNotIn(text, self.maintainer_docs)


if __name__ == "__main__":
    unittest.main()
