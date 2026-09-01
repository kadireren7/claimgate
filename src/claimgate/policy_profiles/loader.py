"""Bounded, strict JSON/YAML loading with no executable configuration features."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from claimgate.policy_profiles.models import PolicyProfile

MAX_POLICY_BYTES = 64 * 1024


class PolicyConfigurationError(ValueError):
    """Raised when untrusted policy configuration cannot be validated."""


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PolicyConfigurationError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise PolicyConfigurationError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class PolicyProfileLoader:
    @classmethod
    def loads(cls, content: str, *, format: str) -> PolicyProfile:
        encoded = content.encode("utf-8")
        if not encoded or len(encoded) > MAX_POLICY_BYTES:
            raise PolicyConfigurationError(
                f"Policy configuration must be 1-{MAX_POLICY_BYTES} UTF-8 bytes"
            )
        try:
            if format.lower() == "json":
                raw = json.loads(content, object_pairs_hook=_reject_duplicate_json_keys)
            elif format.lower() in {"yaml", "yml"}:
                raw = yaml.load(content, Loader=_UniqueKeySafeLoader)
            else:
                raise PolicyConfigurationError("Policy format must be JSON or YAML")
        except PolicyConfigurationError:
            raise
        except (json.JSONDecodeError, yaml.YAMLError, UnicodeError) as exc:
            raise PolicyConfigurationError("Malformed policy configuration") from exc
        if not isinstance(raw, dict):
            raise PolicyConfigurationError("Policy configuration must be an object")
        try:
            return PolicyProfile.model_validate(raw)
        except ValidationError as exc:
            raise PolicyConfigurationError("Invalid policy configuration") from exc

    @classmethod
    def load_path(cls, path: Path) -> PolicyProfile:
        suffix = path.suffix.lower().lstrip(".")
        if suffix not in {"json", "yaml", "yml"}:
            raise PolicyConfigurationError("Policy file must use .json, .yaml, or .yml")
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise PolicyConfigurationError("Policy file could not be read") from exc
        return cls.loads(content, format=suffix)
