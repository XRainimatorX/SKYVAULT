"""Hashing = one fingerprint per input and per result, independent of key order."""

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """
    The one JSON text a value has: keys sorted, no spaces, UTF-8 characters kept.

    Important:
    Two dicts with the same content always give the same text, whatever order
    their keys were inserted in, so their hashes match.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(value: Any) -> str:
    """SHA-256 of the canonical JSON, as 64 hex characters."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def input_hash(scenario: dict[str, Any], evaluation_profile: dict[str, Any]) -> str:
    """
    Fingerprint of everything a run was given.

    Important:
    The profile is part of the input: the same scenario judged under another
    profile is a different run with a different result package.
    """
    return content_hash(
        {"scenario": scenario, "evaluation_profile": evaluation_profile}
    )


def output_hash(result_package: dict[str, Any]) -> str:
    """
    Fingerprint of what a run produced.

    Important:
    The reproducibility block is left out: it records when the run happened,
    which no rerun can repeat. Everything else must match bit for bit for two
    runs to count as the same result.
    """
    produced = {
        key: value for key, value in result_package.items() if key != "reproducibility"
    }
    return content_hash(produced)
