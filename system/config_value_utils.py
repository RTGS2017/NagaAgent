"""Configuration value placeholder helpers."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any


PLACEHOLDER_API_KEYS = frozenset(
    {
        "",
        "your-api-key",
        "your-api-key-here",
        "sk-placeholder-key-not-set",
    }
)


def normalize_api_key(value: Any) -> str:
    """Return a stripped API key string."""
    return str(value or "").strip()


def is_placeholder_api_key(value: Any) -> bool:
    """Return whether a value is empty or one of the built-in placeholder keys."""
    return normalize_api_key(value) in PLACEHOLDER_API_KEYS


def _get_block_value(source: Mapping[str, Any] | object, block_name: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(block_name)
    return getattr(source, block_name, None)


def _get_key_value(source: Mapping[str, Any] | object | None, key_name: str) -> Any:
    if source is None:
        return None
    if isinstance(source, Mapping):
        return source.get(key_name)
    return getattr(source, key_name, None)


def preserve_existing_api_key_if_placeholder(
    payload: MutableMapping[str, Any],
    current_config: Mapping[str, Any] | object,
) -> None:
    """Prevent frontend placeholder values from overwriting an existing real LLM key."""
    api_payload = payload.get("api")
    if not isinstance(api_payload, MutableMapping):
        return

    next_key = api_payload.get("api_key")
    if not is_placeholder_api_key(next_key):
        return

    current_api = _get_block_value(current_config, "api")
    current_key = _get_key_value(current_api, "api_key")
    if is_placeholder_api_key(current_key):
        return

    api_payload["api_key"] = normalize_api_key(current_key)
