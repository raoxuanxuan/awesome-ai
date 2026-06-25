#!/usr/bin/env python3
"""Summarize a tweet payload for Twitter Monitor notifications."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 30


def env_value(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def load_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        raise ValueError("stdin JSON payload is required")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("stdin payload must be a JSON object")
    return data


def api_defaults() -> tuple[str, str, str]:
    api_key = env_value("TWITTER_MONITOR_LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("TWITTER_MONITOR_LLM_API_KEY, DEEPSEEK_API_KEY, or OPENAI_API_KEY is required")

    has_deepseek = bool(env_value("TWITTER_MONITOR_LLM_API_KEY", "DEEPSEEK_API_KEY"))
    base_url = os.environ.get("TWITTER_MONITOR_LLM_BASE_URL")
    if not base_url:
        base_url = "https://api.deepseek.com/chat/completions" if has_deepseek else "https://api.openai.com/v1/chat/completions"

    model = os.environ.get("TWITTER_MONITOR_LLM_MODEL")
    if not model:
        model = "deepseek-chat" if has_deepseek else "gpt-4o-mini"
    return api_key, base_url, model


def request_summary(payload: dict[str, Any]) -> str:
    api_key, base_url, model = api_defaults()
    text = str(payload.get("text") or "").strip()
    max_chars = int(payload.get("max_chars") or 300)
    username = str(payload.get("username") or "")
    types = ", ".join(str(item) for item in payload.get("types") or [])

    prompt = (
        "请把下面的 X/Twitter 内容摘要成适合飞书卡片阅读的中文短摘要。"
        f"最多 {max_chars} 个中文字符。"
        "不要添加字段名、标题、项目符号、评价等级或不存在的信息；保留关键数字、公司名、ticker 和因果关系。\n\n"
        f"作者: {username}\n"
        f"类型: {types}\n"
        f"内容:\n{text}"
    )
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You produce concise, faithful Chinese summaries for notification cards."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 300,
    }
    req = urllib.request.Request(
        base_url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    timeout = int(os.environ.get("TWITTER_MONITOR_LLM_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT_SECONDS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM HTTP {exc.code}: {detail[:500]}") from exc
    loaded = json.loads(raw)
    choices = loaded.get("choices") if isinstance(loaded, dict) else None
    if not choices:
        raise RuntimeError("LLM response missing choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    summary = str((message or {}).get("content") or "").strip()
    if not summary:
        raise RuntimeError("LLM response summary is empty")
    return summary


def main() -> int:
    payload = load_payload()
    summary = request_summary(payload)
    print(json.dumps({"summary": summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
