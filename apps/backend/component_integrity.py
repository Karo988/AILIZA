"""Deterministic integrity helpers for governed components."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(k): _json_value(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple, set, frozenset)):
        normalized = [_json_value(v) for v in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_canonical(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def candidate_hash(values: dict[str, Any]) -> str:
    fields = (
        "provider", "model_id", "modalities", "capabilities",
        "context_window", "regions", "benchmark_version", "evidence_urls",
    )
    return sha256_canonical({field: values.get(field) for field in fields})


def provider_profile_hash(profile: Any) -> str:
    return sha256_canonical(profile)


def approval_basis_hash(*, candidate_object_hash: str,
                        provider_profile_hash_value: str,
                        provider_profile_version: str,
                        task_package: str, purpose: str,
                        allowed_data_classes: list[str], cost_limit: float,
                        policy_version: str) -> str:
    return sha256_canonical({
        "candidate_object_hash": candidate_object_hash,
        "provider_profile_hash": provider_profile_hash_value,
        "provider_profile_version": provider_profile_version,
        "task_package": task_package,
        "purpose": purpose,
        "allowed_data_classes": allowed_data_classes,
        "cost_limit": cost_limit,
        "policy_version": policy_version,
    })
