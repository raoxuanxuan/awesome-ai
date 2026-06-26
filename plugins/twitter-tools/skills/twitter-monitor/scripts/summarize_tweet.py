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
    quote_instruction = ""
    if "quote" in {str(item).lower() for item in payload.get("types") or []}:
        quote_instruction = (
            "如果内容包含引用推文，必须分成两段：第一段只概括作者自己的发言或反应；"
            "空一行后第二段以“引用:”开头，概括被引用推文的内容和来源。"
            "不要把引用推文内容写成作者自己的观点。"
        )

    prompt = (
        "请把下面的 X/Twitter 内容摘要成适合飞书卡片阅读的中文短摘要。"
        f"最多 {max_chars} 个中文字符。"
        "在不重复、不编造的前提下尽量充分，优先覆盖背景、核心观点、关键数字、公司名、ticker、因果关系和投资含义。"
        "不要添加标题、项目符号、评价等级或不存在的信息。"
        f"{quote_instruction}\n\n"
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
        "max_tokens": min(max(300, max_chars * 2), 1200),
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
