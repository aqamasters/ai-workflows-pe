from aqa_ai_workflows_pe.adapters.ai.schema import provider_review_schema


def walk(node: object) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node.get("properties", {}))
        for value in node.values():
            walk(value)
    elif isinstance(node, list):
        for value in node:
            walk(value)


def test_provider_schema_is_strict_for_every_object() -> None:
    schema = provider_review_schema()
    walk(schema)
    assert "default" not in str(schema)
