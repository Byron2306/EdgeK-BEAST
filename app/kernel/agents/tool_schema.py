"""JSON-Schema validation for the centralized tool registry (Phase 6).

The Zod models in ``zod_schemas.py`` / ``zod_schemas_v2.py`` export JSON Schema
(``model_json_schema()`` / ``to_zod_schema()``). This module validates tool
arguments and results against that subset without pulling in a jsonschema
dependency, and reports every failure with a JSON path so the planner can
repair its call instead of guessing.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence


class SchemaValidationError(ValueError):
    def __init__(self, errors: Sequence[Dict[str, str]]) -> None:
        self.errors = list(errors)
        summary = "; ".join(f"{item['path']}: {item['message']}" for item in self.errors)
        super().__init__(summary or "schema validation failed")


_TYPE_CHECKS = {
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, (list, tuple)),
    "string": lambda value: isinstance(value, str),
    "boolean": lambda value: isinstance(value, bool),
    "null": lambda value: value is None,
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
}


def validate_schema(value: Any, schema: Any, *, path: str = "$") -> Any:
    """Validate ``value`` and return it, raising :class:`SchemaValidationError`."""
    errors: List[Dict[str, str]] = []
    _validate(value, schema, path, errors)
    if errors:
        raise SchemaValidationError(errors)
    return value


def is_valid(value: Any, schema: Any) -> bool:
    try:
        validate_schema(value, schema)
        return True
    except SchemaValidationError:
        return False


def _error(errors: List[Dict[str, str]], path: str, message: str) -> None:
    errors.append({"path": path, "message": message})


def _matches_type(value: Any, expected: str) -> bool:
    check = _TYPE_CHECKS.get(expected)
    return True if check is None else check(value)


def _validate(value: Any, schema: Any, path: str, errors: List[Dict[str, str]]) -> None:
    if not isinstance(schema, dict):
        return
    if value is None and bool(schema.get("nullable")):
        return

    declared = schema.get("type")
    types = [declared] if isinstance(declared, str) else list(declared or [])
    if types and not any(_matches_type(value, item) for item in types):
        _error(errors, path, f"expected {'/'.join(types)}, got {type(value).__name__}")
        return

    if "const" in schema and value != schema["const"]:
        _error(errors, path, f"expected constant {schema['const']!r}")
    if isinstance(schema.get("enum"), list) and value not in schema["enum"]:
        _error(errors, path, f"expected one of {schema['enum']!r}, got {value!r}")

    if isinstance(value, str):
        _validate_string(value, schema, path, errors)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        _validate_number(value, schema, path, errors)
    elif isinstance(value, dict):
        _validate_object(value, schema, path, errors)
    elif isinstance(value, (list, tuple)):
        _validate_array(value, schema, path, errors)

    if isinstance(schema.get("allOf"), list):
        for item in schema["allOf"]:
            _validate(value, item, path, errors)
    if isinstance(schema.get("anyOf"), list):
        if not any(is_valid(value, item) for item in schema["anyOf"]):
            _error(errors, path, "value does not match any allowed variant")
    if isinstance(schema.get("oneOf"), list):
        matches = sum(1 for item in schema["oneOf"] if is_valid(value, item))
        if matches != 1:
            _error(errors, path, f"value must match exactly one variant (matched {matches})")


def _validate_string(value: str, schema: Dict[str, Any], path: str, errors: List[Dict[str, str]]) -> None:
    if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
        _error(errors, path, f"shorter than minLength {schema['minLength']}")
    if isinstance(schema.get("maxLength"), int) and len(value) > schema["maxLength"]:
        _error(errors, path, f"longer than maxLength {schema['maxLength']}")
    pattern = schema.get("pattern")
    if isinstance(pattern, str):
        try:
            if re.search(pattern, value) is None:
                _error(errors, path, f"does not match pattern {pattern!r}")
        except re.error:
            pass


def _validate_number(value: float, schema: Dict[str, Any], path: str, errors: List[Dict[str, str]]) -> None:
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    if isinstance(minimum, (int, float)) and value < minimum:
        _error(errors, path, f"less than minimum {minimum}")
    if isinstance(maximum, (int, float)) and value > maximum:
        _error(errors, path, f"greater than maximum {maximum}")
    exclusive_min = schema.get("exclusiveMinimum")
    exclusive_max = schema.get("exclusiveMaximum")
    if isinstance(exclusive_min, (int, float)) and value <= exclusive_min:
        _error(errors, path, f"not greater than {exclusive_min}")
    if isinstance(exclusive_max, (int, float)) and value >= exclusive_max:
        _error(errors, path, f"not less than {exclusive_max}")


def _validate_object(value: Dict[str, Any], schema: Dict[str, Any], path: str, errors: List[Dict[str, str]]) -> None:
    properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
    required = schema.get("required") if isinstance(schema.get("required"), list) else []
    for name in required:
        if name not in value:
            _error(errors, f"{path}.{name}", "required property is missing")
    for name, item in properties.items():
        if name in value:
            _validate(value[name], item, f"{path}.{name}", errors)

    additional = schema.get("additionalProperties")
    extras = [name for name in value if name not in properties]
    if additional is False and extras:
        _error(errors, path, f"unexpected properties: {', '.join(sorted(extras))}")
    elif isinstance(additional, dict):
        for name in extras:
            _validate(value[name], additional, f"{path}.{name}", errors)


def _validate_array(value: Sequence[Any], schema: Dict[str, Any], path: str, errors: List[Dict[str, str]]) -> None:
    if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
        _error(errors, path, f"fewer than minItems {schema['minItems']}")
    if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
        _error(errors, path, f"more than maxItems {schema['maxItems']}")
    items = schema.get("items")
    if isinstance(items, dict):
        for index, item in enumerate(value):
            _validate(item, items, f"{path}[{index}]", errors)
    elif isinstance(items, list):
        for index, item in enumerate(value[: len(items)]):
            _validate(item, items[index], f"{path}[{index}]", errors)
