import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kol_rollout import build_plan


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


class KolRolloutTests(unittest.TestCase):
    def test_build_plan_routes_bootstrap_and_incremental_handles(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            for handle in ["bootstrap", "mature"]:
                wiki = vault / handle / "wiki"
                wiki.mkdir(parents=True)
                write_jsonl(
                    wiki / ".clean_corpus.jsonl",
                    [{"id": "1", "text": "x", "quality": "high", "routing": {"distill": True}}],
                )
                write_jsonl(wiki / ".ingest_index.jsonl", [{"id": "1", "text": "x"}])
                (wiki / ".ingest_stats.json").write_text(
                    json.dumps({"total": 1, "source": str(wiki / ".clean_corpus.jsonl")}),
                    encoding="utf-8",
                )
            mature = vault / "mature" / "wiki"
            for name in ["_index.md", "soul.md", "timeline.md"]:
                (mature / name).write_text("# ok\n- 12345678\n", encoding="utf-8")
            for subdir in ["sources", "methods", "positions"]:
                (mature / subdir).mkdir()
                (mature / subdir / "sample.md").write_text("# sample\n\n## Evidence\n- 12345678\n", encoding="utf-8")

            plan = build_plan(vault, handles=["bootstrap", "mature"])

            actions = {item["handle"]: item["action"] for item in plan["items"]}
            self.assertEqual(actions["bootstrap"], "bootstrap-pack")
            self.assertEqual(actions["mature"], "delta")


if __name__ == "__main__":
    unittest.main()
