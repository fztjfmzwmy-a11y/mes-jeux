"""Chaînage SHA-256 du journal : toute modification a posteriori devient détectable."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel

GENESIS_HASH = "0" * 64


def canonical_json(model: BaseModel) -> str:
    data: Any = model.model_dump(mode="json")
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def entry_hash(seq: int, prev_hash: str, payload: str) -> str:
    material = f"{seq}\n{prev_hash}\n{payload}".encode()
    return hashlib.sha256(material).hexdigest()
