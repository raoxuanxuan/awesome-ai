import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kol_wiki_inventory import classify_handle, inventory_vault


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


class KolWikiInventoryTests(unittest.TestCase):
    def test_classifies_mature_wiki_with_clean_index_and_core_pages(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            wiki = vault / "h" / "wiki"
            wiki.mkdir(parents=True)
            write_jsonl(wiki / ".clean_corpus.jsonl", [{"id": "1", "text": "x", "routing": {"distill": True}}])
            write_jsonl(wiki / ".ingest_index.jsonl", [{"id": "1", "text": "x"}])
            (wiki / ".ingest_stats.json").write_text(
                json.dumps({"total": 1, "source": str(wiki / ".clean_corpus.jsonl")}),
                encoding="utf-8",
            )
            for name in ["_index.md", "soul.md", "timeline.md"]:
                (wiki / name).write_text(f"# {name}\n", encoding="utf-8")
            for subdir in ["sources", "methods", "positions"]:
                (wiki / subdir).mkdir()
                (wiki / subdir / "sample.md").write_text("# sample\n\n## Evidence\n- 1\n", encoding="utf-8")

            result = classify_handle(vault, "h")

            self.assertEqual(result["route"], "existing_mature_wiki")
            self.assertEqual(result["clean_count"], 1)
            self.assertTrue(result["index_source_is_clean"])

    def test_classifies_no_wiki_as_bootstrap_required(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            wiki = vault / "h" / "wiki"
            wiki.mkdir(parents=True)
            write_jsonl(wiki / ".clean_corpus.jsonl", [{"id": "1", "text": "x", "routing": {"distill": True}}])
            write_jsonl(wiki / ".ingest_index.jsonl", [{"id": "1", "text": "x"}])
            (wiki / ".ingest_stats.json").write_text(
                json.dumps({"total": 1, "source": str(wiki / ".clean_corpus.jsonl")}),
                encoding="utf-8",
            )

            result = classify_handle(vault, "h")

            self.assertEqual(result["route"], "bootstrap_required")
            self.assertIn("missing soul.md", result["issues"])

    def test_inventory_vault_lists_all_handles(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            for handle in ["a", "b"]:
                wiki = vault / handle / "wiki"
                wiki.mkdir(parents=True)
                write_jsonl(wiki / ".clean_corpus.jsonl", [{"id": "1", "text": "x"}])

            result = inventory_vault(vault)

            self.assertEqual([item["handle"] for item in result["handles"]], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
