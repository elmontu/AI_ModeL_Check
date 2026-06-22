"""Thin wrapper for calling LLM endpoints."""

from __future__ import annotations

import os
import time
from typing import Callable


def make_openai_endpoint(
    model: str = "gpt-4o-mini",
    api_key: str | None = None,
    base_url: str | None = None,
    system_prompt: str | None = None,
) -> Callable[[str], str]:
    """Create a callable (str) -> str that calls an OpenAI-compatible endpoint."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Install openai: pip install ai-safety-checker[llm]")

    client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"), base_url=base_url)

    def call(prompt: str) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        response = client.chat.completions.create(model=model, messages=messages)
        return response.choices[0].message.content or ""

    return call


def make_anthropic_endpoint(
    model: str = "claude-sonnet-4-20250514",
    api_key: str | None = None,
    system_prompt: str | None = None,
) -> Callable[[str], str]:
    """Create a callable (str) -> str that calls the Anthropic API."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("Install anthropic: pip install anthropic")

    client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def call(prompt: str) -> str:
        kwargs = {"model": model, "max_tokens": 1024, "messages": [{"role": "user", "content": prompt}]}
        if system_prompt:
            kwargs["system"] = system_prompt
        response = client.messages.create(**kwargs)
        return response.content[0].text

    return call


def rate_limited(endpoint: Callable[[str], str], delay: float = 1.0) -> Callable[[str], str]:
    """Wrap an endpoint with a delay between calls to avoid rate limits."""
    def call(prompt: str) -> str:
        result = endpoint(prompt)
        time.sleep(delay)
        return result
    return call
