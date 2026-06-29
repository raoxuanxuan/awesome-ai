#!/usr/bin/env python3

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "substack_fetch.py"


def load_module():
    spec = importlib.util.spec_from_file_location("substack_fetch", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SubstackFetchTest(unittest.TestCase):
    def test_parses_substack_post_url(self):
        mod = load_module()

        host, slug = mod.parse_substack_url(
            "https://damnang2.substack.com/p/is-cxmt-a-threat-or-an-illusion?r=1"
        )

        self.assertEqual(host, "damnang2.substack.com")
        self.assertEqual(slug, "is-cxmt-a-threat-or-an-illusion")

    def test_parse_body_extracts_markdown_text_sections_and_media(self):
        mod = load_module()
        body_html = """
        <h2>Intro</h2>
        <p>Hello <strong>world</strong>.</p>
        <figure><img src="https://substackcdn.com/image.jpg" alt="Chart"></figure>
        <h3>Details</h3>
        <ol><li>One</li><li>Two</li></ol>
        <svg><title>Ignore me</title></svg>
        """

        markdown, text, sections, media = mod.parse_body(body_html)

        self.assertIn("## Intro", markdown)
        self.assertIn("Hello **world**.", markdown)
        self.assertIn("![Chart](https://substackcdn.com/image.jpg)", markdown)
        self.assertIn("1. One", markdown)
        self.assertIn("2. Two", markdown)
        self.assertIn("Hello world", text)
        self.assertEqual(sections[0]["title"], "Intro")
        self.assertEqual(sections[1]["title"], "Details")
        self.assertEqual(media[0]["source_url"], "https://substackcdn.com/image.jpg")
        self.assertEqual(media[0]["alt"], "Chart")

    def test_build_content_sets_translation_hint_for_english(self):
        mod = load_module()
        post = {
            "id": 1,
            "slug": "sample-post",
            "canonical_url": "https://example.substack.com/p/sample-post",
            "title": "Sample",
            "subtitle": "Subtitle",
            "post_date": "2026-01-02T00:00:00Z",
            "body_html": "<p>This is an English article about semiconductors.</p>",
            "publishedBylines": [{"name": "Author", "handle": "author"}],
        }

        content = mod.build_content(post, "https://example.substack.com/p/sample-post")

        self.assertEqual(content["source"]["platform"], "substack")
        self.assertEqual(content["lang"], "en")
        self.assertTrue(content["translation"]["preferred"])

    def test_canonical_media_key_dedupes_substack_cdn_variants(self):
        mod = load_module()
        a = (
            "https://substackcdn.com/image/fetch/$s_!a!,w_424,c_limit,f_auto/"
            "https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fx.png"
        )
        b = (
            "https://substackcdn.com/image/fetch/$s_!b!,f_auto/"
            "https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fx.png"
        )

        self.assertEqual(mod.canonical_media_key(a), mod.canonical_media_key(b))

    def test_write_artifacts_creates_expected_files(self):
        mod = load_module()
        post = {
            "id": 1,
            "slug": "sample-post",
            "canonical_url": "https://example.substack.com/p/sample-post",
            "title": "Sample",
            "post_date": "2026-01-02T00:00:00Z",
            "body_html": "<p>Hello world.</p>",
        }
        content = mod.build_content(post, "https://example.substack.com/p/sample-post")

        with tempfile.TemporaryDirectory() as tmp:
            paths = mod.write_artifacts(content, post, Path(tmp), True)

            self.assertTrue(Path(paths["content_json"]).exists())
            self.assertTrue(Path(paths["post_json"]).exists())
            self.assertTrue(Path(paths["body_html"]).exists())
            self.assertTrue(Path(paths["markdown"]).exists())
            self.assertIn("2026-01-02-sample-post", paths["output_dir"])


if __name__ == "__main__":
    unittest.main()
