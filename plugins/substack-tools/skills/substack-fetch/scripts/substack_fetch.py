#!/usr/bin/env python3
"""
Fetch public Substack posts and emit normalized content JSON.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30


def slugify(value: str, default: str = "substack-post") -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-").lower()
    return slug or default


def parse_substack_url(url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("URL must use http or https")
    if not parsed.netloc:
        raise ValueError("URL is missing host")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[-2] != "p":
        raise ValueError("Substack post URL must contain /p/<slug>")
    return parsed.netloc, parts[-1]


def api_url_for_post(url: str) -> str:
    host, slug = parse_substack_url(url)
    return f"https://{host}/api/v1/posts/{slug}"


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        data = response.read().decode("utf-8")
    parsed = json.loads(data)
    if not isinstance(parsed, dict):
        raise ValueError("Substack API response must be a JSON object")
    return parsed


def plain_text_from_html(body_html: str) -> str:
    parser = PlainTextParser()
    parser.feed(body_html)
    return parser.text()


def detect_language(text: str) -> str:
    if not text:
        return "unknown"
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    letters = len(re.findall(r"[A-Za-z]", text))
    if chinese_chars >= max(20, letters // 4):
        return "zh"
    if letters:
        return "en"
    return "unknown"


def translation_hint(lang: str) -> dict[str, Any]:
    preferred = lang not in {"zh", "unknown"}
    return {
        "preferred": preferred,
        "target_lang": "zh-CN",
        "reason": "source language appears non-Chinese" if preferred else "source language appears Chinese or unknown",
    }


def canonical_media_key(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if "substackcdn.com" not in parsed.netloc or "/image/fetch/" not in parsed.path:
        return url
    marker = "/https%3A%2F%2F"
    if marker not in parsed.path:
        return url
    encoded = "https%3A%2F%2F" + parsed.path.rsplit(marker, 1)[-1]
    return urllib.parse.unquote(encoded)


def published_date_prefix(post: dict[str, Any]) -> str:
    raw = post.get("post_date") or post.get("published_at") or ""
    if isinstance(raw, str) and len(raw) >= 10:
        return raw[:10]
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def publication_slug(host: str) -> str:
    first = host.split(".")[0]
    return slugify(first, "substack")


def byline(post: dict[str, Any]) -> tuple[dict[str, str], str]:
    bylines = post.get("publishedBylines") or []
    if not bylines or not isinstance(bylines[0], dict):
        return {"name": "", "handle": ""}, ""

    author_node = bylines[0]
    author = {
        "name": str(author_node.get("name") or ""),
        "handle": str(author_node.get("handle") or ""),
    }
    publication_name = ""
    for publication_user in author_node.get("publicationUsers") or []:
        if not isinstance(publication_user, dict):
            continue
        publication = publication_user.get("publication") or {}
        if isinstance(publication, dict) and publication.get("name"):
            publication_name = str(publication["name"])
            break
    return author, publication_name


class PlainTextParser(HTMLParser):
    skip_container_tags = {"script", "style", "svg", "button", "form"}
    block_tags = {"p", "div", "figure", "figcaption", "blockquote", "li", "hr", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def newline(self) -> None:
        if self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.skip_container_tags:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in self.block_tags or tag == "br":
            self.newline()

    def handle_endtag(self, tag: str) -> None:
        if tag in self.skip_container_tags:
            if self.skip_depth:
                self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag in self.block_tags:
            self.newline()

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = re.sub(r"\s+", " ", data)
        if text.strip():
            self.parts.append(text)

    def text(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


class MediaAndMarkdownParser(HTMLParser):
    skip_container_tags = {"script", "style", "svg", "button", "form"}
    ignore_tags = {"input", "source", "path", "polyline", "line", "g"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.media: list[dict[str, Any]] = []
        self.skip_depth = 0
        self.list_stack: list[dict[str, Any]] = []
        self.link_stack: list[dict[str, Any]] = []
        self.emphasis: list[str] = []
        self.heading_level: int | None = None
        self.heading_text: list[str] = []
        self.sections: list[dict[str, Any]] = []

    def write(self, text: str) -> None:
        if text:
            self.parts.append(text)

    def newline(self, count: int = 1) -> None:
        current = "".join(self.parts)
        existing = len(current) - len(current.rstrip("\n"))
        if existing < count:
            self.parts.append("\n" * (count - existing))

    def sink_write(self, text: str) -> None:
        if self.heading_level is not None:
            self.heading_text.append(text)
        if self.link_stack:
            self.link_stack[-1]["text"].append(text)
        else:
            self.write(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        if tag in self.skip_container_tags:
            self.skip_depth += 1
            return
        if tag in self.ignore_tags or self.skip_depth:
            return
        if tag in {"p", "div", "figure", "figcaption"}:
            self.newline(2)
        elif tag == "br":
            self.newline(1)
        elif tag == "hr":
            self.newline(2)
            self.write("---")
            self.newline(2)
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(tag[1])
            self.heading_level = level
            self.heading_text = []
            self.newline(2)
            self.write("#" * level + " ")
        elif tag in {"strong", "b"}:
            self.sink_write("**")
            self.emphasis.append("**")
        elif tag in {"em", "i"}:
            self.sink_write("*")
            self.emphasis.append("*")
        elif tag == "blockquote":
            self.newline(2)
            self.write("> ")
        elif tag in {"ul", "ol"}:
            self.list_stack.append({"tag": tag, "n": 0})
            self.newline(1)
        elif tag == "li":
            self.newline(1)
            indent = "  " * max(0, len(self.list_stack) - 1)
            if self.list_stack and self.list_stack[-1]["tag"] == "ol":
                self.list_stack[-1]["n"] += 1
                self.write(f"{indent}{self.list_stack[-1]['n']}. ")
            else:
                self.write(f"{indent}- ")
        elif tag == "a":
            self.link_stack.append({"href": attrs_dict.get("href", ""), "text": []})
        elif tag == "img":
            source_url = attrs_dict.get("src", "")
            alt = re.sub(r"\s+", " ", attrs_dict.get("alt", "")).strip()
            if source_url:
                self.add_media(source_url, alt)
                self.newline(2)
                self.write(f"![{alt or 'image'}]({source_url})")
                self.newline(2)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.skip_container_tags:
            if self.skip_depth:
                self.skip_depth -= 1
            return
        if tag in self.ignore_tags or self.skip_depth:
            return
        if tag in {"strong", "b", "em", "i"} and self.emphasis:
            self.sink_write(self.emphasis.pop())
        elif tag == "a" and self.link_stack:
            link = self.link_stack.pop()
            text = "".join(link["text"]).strip()
            href = link["href"]
            if text:
                rendered = f"[{text}]({href})" if href else text
                if self.link_stack:
                    self.link_stack[-1]["text"].append(rendered)
                else:
                    self.write(rendered)
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            title = re.sub(r"\s+", " ", "".join(self.heading_text)).strip("* ")
            if title and self.heading_level is not None:
                self.sections.append({"level": self.heading_level, "title": title, "text": ""})
            self.heading_level = None
            self.heading_text = []
            self.newline(2)
        elif tag in {"p", "div", "figure", "figcaption", "blockquote", "ul", "ol"}:
            if tag in {"ul", "ol"} and self.list_stack:
                self.list_stack.pop()
            self.newline(2)

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = re.sub(r"\s+", " ", data)
        if text.strip():
            self.sink_write(text)

    def add_media(self, source_url: str, alt: str, role: str | None = None) -> None:
        source_key = canonical_media_key(source_url)
        if any(item.get("canonical_url") == source_key for item in self.media):
            return
        self.media.append(
            {
                "source_url": source_url,
                "canonical_url": source_key,
                "alt": alt,
                "kind": "image",
                "role": role or ("cover" if not self.media else "inline"),
            }
        )

    def markdown(self) -> str:
        markdown = "".join(self.parts)
        markdown = re.sub(r"[ \t]+\n", "\n", markdown)
        markdown = re.sub(r"\n{3,}", "\n\n", markdown)
        markdown = re.sub(r" +", " ", markdown)
        markdown = re.sub(r"\n(\d+)\.\n\n", r"\n\1. ", markdown)
        return markdown.strip() + "\n"


def parse_body(body_html: str) -> tuple[str, str, list[dict[str, Any]], list[dict[str, Any]]]:
    parser = MediaAndMarkdownParser()
    parser.feed(body_html)
    markdown = parser.markdown()
    text = plain_text_from_html(body_html)
    sections = fill_section_text(parser.sections, text)
    return markdown, text, sections, parser.media


def fill_section_text(sections: list[dict[str, Any]], text: str) -> list[dict[str, Any]]:
    if not sections:
        return []
    result = []
    for index, section in enumerate(sections):
        title = section["title"]
        start = text.find(title)
        end = -1
        for next_section in sections[index + 1 :]:
            next_start = text.find(next_section["title"], start + len(title) if start >= 0 else 0)
            if next_start >= 0:
                end = next_start
                break
        if start >= 0:
            body = text[start + len(title) : end if end >= 0 else None].strip()
        else:
            body = ""
        item = dict(section)
        item["text"] = body
        result.append(item)
    return result


def build_content(post: dict[str, Any], input_url: str) -> dict[str, Any]:
    canonical_url = post.get("canonical_url") or urllib.parse.urlunparse(
        urllib.parse.urlparse(input_url)._replace(query="", fragment="")
    )
    host, slug = parse_substack_url(canonical_url)
    body_html = str(post.get("body_html") or "")
    markdown, text, sections, media = parse_body(body_html)
    cover_image = post.get("cover_image")
    if isinstance(cover_image, str) and cover_image:
        cover_key = canonical_media_key(cover_image)
        if not any(item.get("canonical_url") == cover_key for item in media):
            media.insert(0, {"source_url": cover_image, "canonical_url": cover_key, "alt": "", "kind": "image", "role": "cover"})
    author, publication_name = byline(post)
    lang = detect_language(text)

    return {
        "source": {
            "platform": "substack",
            "url": canonical_url,
            "original_url": input_url,
            "id": str(post.get("id") or ""),
            "slug": str(post.get("slug") or slug),
            "publication": host,
            "publication_name": publication_name,
        },
        "author": author,
        "title": str(post.get("title") or ""),
        "subtitle": str(post.get("subtitle") or post.get("description") or ""),
        "published_at": post.get("post_date"),
        "updated_at": post.get("updated_at"),
        "lang": lang,
        "content_type": "article",
        "text": text,
        "markdown": markdown,
        "html": body_html,
        "sections": sections,
        "media": media,
        "stats": {
            "wordcount": post.get("wordcount"),
            "reactions": post.get("reactions") or {},
            "comment_count": post.get("comment_count"),
            "restacks": post.get("restacks"),
        },
        "translation": translation_hint(lang),
        "references": [],
    }


def frontmatter_value(value: Any) -> str:
    return json.dumps(value if value is not None else "", ensure_ascii=False)


def render_original_markdown(content: dict[str, Any]) -> str:
    title = content.get("title") or "Untitled"
    source = content.get("source") or {}
    stats = content.get("stats") or {}
    lines = [
        "---",
        f"title: {frontmatter_value(title)}",
        f"subtitle: {frontmatter_value(content.get('subtitle'))}",
        f"author: {frontmatter_value((content.get('author') or {}).get('name'))}",
        f"publication: {frontmatter_value(source.get('publication_name'))}",
        f"source: {frontmatter_value(source.get('url'))}",
        f"original_url: {frontmatter_value(source.get('original_url'))}",
        f"post_date: {frontmatter_value(content.get('published_at'))}",
        f"updated_at: {frontmatter_value(content.get('updated_at'))}",
        f"substack_post_id: {frontmatter_value(source.get('id'))}",
        f"wordcount: {stats.get('wordcount') if stats.get('wordcount') is not None else 'null'}",
        f"lang: {frontmatter_value(content.get('lang'))}",
        "translation_preferred: " + str(bool((content.get("translation") or {}).get("preferred"))).lower(),
        "tags: [substack]",
        f"archived_at: {frontmatter_value(datetime.now(timezone.utc).isoformat())}",
        "---",
        "",
        f"# {title}",
        "",
    ]
    if content.get("subtitle"):
        lines.extend([str(content["subtitle"]), ""])
    if source.get("url"):
        lines.extend([f"Original: [{source['url']}]({source['url']})", ""])
    lines.append(str(content.get("markdown") or "").strip())
    lines.append("")
    return "\n".join(lines)


def write_artifacts(content: dict[str, Any], post: dict[str, Any], output_root: Path, emit_markdown: bool) -> dict[str, str]:
    source = content["source"]
    date_prefix = published_date_prefix(post)
    slug = slugify(str(source.get("slug") or content.get("title") or "substack-post"))
    out_dir = output_root / publication_slug(str(source["publication"])) / f"{date_prefix}-{slug}"
    out_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, str] = {"output_dir": str(out_dir)}
    content_json = out_dir / "content.json"
    content_json.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["content_json"] = str(content_json)

    post_json = out_dir / "post.json"
    post_json.write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["post_json"] = str(post_json)

    body_html = out_dir / "body.html"
    body_html.write_text(str(post.get("body_html") or ""), encoding="utf-8")
    paths["body_html"] = str(body_html)

    if emit_markdown:
        markdown_path = out_dir / f"{date_prefix}-{slug}.md"
        markdown_path.write_text(render_original_markdown(content), encoding="utf-8")
        paths["markdown"] = str(markdown_path)

    return paths


def fetch_post(input_url: str, output_root: Path | None = None, write_files: bool = True, emit_markdown: bool = True) -> dict[str, Any]:
    post = fetch_json(api_url_for_post(input_url))
    content = build_content(post, input_url)
    paths: dict[str, str] = {}
    if write_files:
        if output_root is None:
            output_root = Path.home() / "Downloads" / "substack"
        paths = write_artifacts(content, post, output_root.expanduser(), emit_markdown)
    return {"ok": True, "content": content, "paths": paths}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch public Substack posts")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser("fetch", help="Fetch a Substack post")
    fetch.add_argument("--url", required=True, help="Substack post URL")
    fetch.add_argument("--out", help="Output root, defaults to ~/Downloads/substack")
    fetch.add_argument("--no-artifacts", action="store_true", help="Do not write local files")
    fetch.add_argument("--emit-markdown", choices=["true", "false"], default="true", help="Write original Markdown artifact")
    fetch.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = fetch_post(
            args.url,
            Path(args.out).expanduser() if args.out else None,
            write_files=not args.no_artifacts,
            emit_markdown=args.emit_markdown == "true",
        )
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        print(json.dumps(result, ensure_ascii=False, indent=2 if getattr(args, "pretty", False) else None))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
