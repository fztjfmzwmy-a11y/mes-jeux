"""Validation des identifiants d'instruments."""

from __future__ import annotations

import re

_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def is_valid_isin(isin: str) -> bool:
    """Vérifie le format et la clé de contrôle (Luhn) d'un ISIN."""
    if not _ISIN_RE.match(isin):
        return False
    digits = "".join(str(int(c, 36)) for c in isin[:-1])
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return (10 - total % 10) % 10 == int(isin[-1])


def normalize_isin(value: str) -> str:
    isin = value.strip().upper()
    if not is_valid_isin(isin):
        raise ValueError(f"ISIN invalide : {value!r}")
    return isin
