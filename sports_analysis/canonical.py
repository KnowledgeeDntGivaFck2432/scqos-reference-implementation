"""Canonical hashing shared by the sports API and Shadow Clone receipts."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any


def normalize_for_hash(value: Any) -> Any:
    """Normalize DynamoDB values without losing non-integral decimal precision."""

    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("NON_FINITE_DECIMAL")
        if value == value.to_integral_value():
            return int(value)
        return format(value.normalize(), "f")
    if isinstance(value, float):
        raise TypeError("FLOAT_NOT_SUPPORTED_IN_CANONICAL_RECEIPT")
    if isinstance(value, dict):
        return {str(key): normalize_for_hash(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_for_hash(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [normalize_for_hash(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True, default=str))
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        normalize_for_hash(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def receipt_sha256(item: dict[str, Any]) -> str:
    return sha256({key: value for key, value in item.items() if key != "receipt_sha256"})
