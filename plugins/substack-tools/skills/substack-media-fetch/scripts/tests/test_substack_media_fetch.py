#!/usr/bin/env python3

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "substack_media_fetch.py"


def load_module():
    spec = importlib.util.spec_from_file_location("substack_media_fetch", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SubstackMediaFetchTest(unittest.TestCase):
    def test_collects_unique_urls_from_content_json(self):
        mod = load_module()
        payload = {
            "media": [
                {"source_url": "https://substackcdn.com/a.jpg"},
                {"source_url": "https://substackcdn.com/a.jpg"},
                {"url": "https://substackcdn.com/b.png"},
            ]
        }

        urls = mod.collect_media_urls(payload)

        self.assertEqual(urls, ["https://substackcdn.com/a.jpg", "https://substackcdn.com/b.png"])

    def test_collects_unique_substack_cdn_variants(self):
        mod = load_module()
        a = (
            "https://substackcdn.com/image/fetch/$s_!a!,w_424,c_limit,f_auto/"
            "https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fx.png"
        )
        b = (
            "https://substackcdn.com/image/fetch/$s_!b!,f_auto/"
            "https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fx.png"
        )

        urls = mod.collect_media_urls({"media": [{"source_url": a}, {"source_url": b}]})

        self.assertEqual(urls, [a])

    def test_download_writes_manifest(self):
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

            self.assertTrue(manifest["ok"])
            self.assertEqual(manifest["count"], 2)
            self.assertEqual(manifest["downloaded"][0]["filename"], "sample-cover.jpg")
            self.assertEqual(manifest["downloaded"][1]["filename"], "sample-img01.png")
            self.assertEqual((output_dir / "sample-cover.jpg").read_bytes(), b"aaa")
            self.assertEqual((output_dir / "sample-img01.png").read_bytes(), b"bbb")
            self.assertEqual(len(manifest["downloaded"][0]["sha256"]), 64)

    def test_cli_accepts_fetch_envelope(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source.jpg"
            source.write_bytes(b"image")
            input_path = tmp_path / "content.json"
            input_path.write_text(
                json.dumps({"ok": True, "content": {"media": [{"source_url": source.as_uri()}]}}),
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
