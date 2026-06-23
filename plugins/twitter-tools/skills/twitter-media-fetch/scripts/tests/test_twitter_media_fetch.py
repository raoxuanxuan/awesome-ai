#!/usr/bin/env python3

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "twitter_media_fetch.py"


def load_module():
    spec = importlib.util.spec_from_file_location("twitter_media_fetch", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TwitterMediaFetchTest(unittest.TestCase):
    def test_collects_media_from_article_thread_and_quote(self):
        mod = load_module()
        envelope = {
            "ok": True,
            "items": [
                {
                    "id": "1",
                    "article": {"images": ["https://pbs.twimg.com/article.jpg?format=jpg"]},
                    "media": [{"url": "https://pbs.twimg.com/main.webp"}],
                    "thread": {
                        "items": [
                            {"media": [{"media_url_https": "https://pbs.twimg.com/thread.png"}]}
                        ]
                    },
                    "quote": {
                        "media": {
                            "images": [
                                {"url": "https://pbs.twimg.com/quote.jpg?format=jpg"}
                            ]
                        }
                    },
                }
            ],
        }

        urls = mod.collect_media_urls(envelope)

        self.assertEqual(
            urls,
            [
                "https://pbs.twimg.com/article.jpg?format=jpg",
                "https://pbs.twimg.com/main.webp",
                "https://pbs.twimg.com/thread.png",
                "https://pbs.twimg.com/quote.jpg?format=jpg",
            ],
        )

    def test_download_writes_manifest_with_slug_names(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_a = tmp_path / "source-a.jpg"
            source_b = tmp_path / "source-b.png"
            source_a.write_bytes(b"aaa")
            source_b.write_bytes(b"bbb")
            output_dir = tmp_path / "assets"

            manifest = mod.download_media(
                [source_a.as_uri(), source_b.as_uri()],
                output_dir,
                "sample",
            )

            self.assertEqual(manifest["count"], 2)
            self.assertEqual(manifest["failed"], [])
            self.assertEqual(manifest["downloaded"][0]["filename"], "sample-cover.jpg")
            self.assertEqual(manifest["downloaded"][1]["filename"], "sample-img01.png")
            self.assertEqual((output_dir / "sample-cover.jpg").read_bytes(), b"aaa")
            self.assertEqual((output_dir / "sample-img01.png").read_bytes(), b"bbb")
            self.assertEqual(manifest["downloaded"][0]["media_type"], "image")
            self.assertEqual(len(manifest["downloaded"][0]["sha256"]), 64)

    def test_cli_reads_input_and_prints_json_manifest(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source.jpg"
            source.write_bytes(b"image")
            input_path = tmp_path / "tweet.json"
            input_path.write_text(
                json.dumps({"ok": True, "items": [{"media": [{"url": source.as_uri()}]}]}),
                encoding="utf-8",
            )
            output_dir = tmp_path / "assets"

            with redirect_stdout(io.StringIO()):
                exit_code = mod.main(
                    [
                        "download",
                        "--input",
                        str(input_path),
                        "--output-dir",
                        str(output_dir),
                        "--prefix",
                        "from-cli",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue((output_dir / "from-cli-cover.jpg").exists())


if __name__ == "__main__":
    unittest.main()
