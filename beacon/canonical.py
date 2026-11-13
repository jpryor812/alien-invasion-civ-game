"""Canonical JSON encoding and hashing.

Everything the simulation writes or hashes goes through here, so equal values always give equal
bytes. NaN and infinity are rejected outright.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def dumps(obj: Any, *, indent: int | None = None) -> str:
    """Encode `obj` as JSON with sorted keys; compact unless `indent` is given."""
    separators = (",", ":") if indent is None else (",", ": ")
    return json.dumps(
        obj,
        sort_keys=True,
        separators=separators,
        indent=indent,
        allow_nan=False,
        ensure_ascii=False,
    )


def digest(obj: Any) -> str:
    """SHA-256 hex digest of the compact canonical encoding of `obj`."""
    return hashlib.sha256(dumps(obj).encode("utf-8")).hexdigest()
