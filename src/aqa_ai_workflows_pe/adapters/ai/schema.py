from __future__ import annotations

from typing import Any

from ...domain.models import ProviderReview


def provider_review_schema() -> dict[str, Any]:
    schema = ProviderReview.model_json_schema()
    _normalize(schema)
    return schema


def _normalize(node: Any, *, property_map: bool = False) -> None:
    if isinstance(node, dict):
        if not property_map:
            node.pop("default", None)
            node.pop("title", None)
        if node.get("type") == "object" or "properties" in node:
            properties = node.get("properties", {})
            node["additionalProperties"] = False
            node["required"] = list(properties)
            _normalize(properties, property_map=True)
        for key, value in node.items():
            if key != "properties":
                _normalize(value)
    elif isinstance(node, list):
        for value in node:
            _normalize(value)
