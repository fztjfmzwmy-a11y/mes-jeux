"""Détection des identifiants et secrets dans les données importées.

AI Investor ne doit jamais recevoir ni stocker : mot de passe, PIN, code 2FA, cookie,
token de session, identifiants bancaires. Tout import qui en contient est refusé
AVANT stockage. Les valeurs détectées ne sont jamais recopiées dans les messages d'erreur.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

from ai_investor.core.errors import SensitiveDataError

# Mots-clés recherchés comme mots entiers dans les noms de champs (snake_case, camelCase, etc.).
SENSITIVE_TOKENS: frozenset[str] = frozenset(
    {
        "password",
        "passwort",
        "passwd",
        "pwd",
        "motdepasse",
        "mdp",
        "pin",
        "tan",
        "otp",
        "2fa",
        "mfa",
        "totp",
        "token",
        "cookie",
        "cookies",
        "session",
        "sessionid",
        "jsessionid",
        "secret",
        "credential",
        "credentials",
        "login",
        "iban",
        "bic",
        "swift",
        "cvv",
        "cvc",
        "apikey",
        "authorization",
        "bearer",
        "refreshtoken",
        "accesstoken",
    }
)
# Combinaisons de mots (ex. « mot de passe », « access token »).
SENSITIVE_PHRASES: tuple[tuple[str, ...], ...] = (
    ("mot", "de", "passe"),
    ("access", "token"),
    ("refresh", "token"),
    ("api", "key"),
    ("card", "number"),
    ("numero", "carte"),
)


def _tokens(field_name: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", field_name)
    return [t for t in re.split(r"[^a-z0-9]+", spaced.lower()) if t]


def is_sensitive_field(field_name: str) -> bool:
    tokens = _tokens(field_name)
    if any(t in SENSITIVE_TOKENS for t in tokens):
        return True
    if "".join(tokens) in SENSITIVE_TOKENS:
        return True
    for phrase in SENSITIVE_PHRASES:
        n = len(phrase)
        if any(tuple(tokens[i : i + n]) == phrase for i in range(len(tokens) - n + 1)):
            return True
    return False


def find_sensitive_fields(data: object, _path: str = "") -> list[str]:
    """Retourne les chemins des champs sensibles trouvés (récursif, dict et listes)."""
    found: list[str] = []
    if isinstance(data, Mapping):
        for key, value in data.items():
            path = f"{_path}.{key}" if _path else str(key)
            if is_sensitive_field(str(key)):
                found.append(path)
            found.extend(find_sensitive_fields(value, path))
    elif isinstance(data, Sequence) and not isinstance(data, str | bytes):
        for index, item in enumerate(data):
            found.extend(find_sensitive_fields(item, f"{_path}[{index}]"))
    return found


def assert_no_sensitive_fields(data: object) -> None:
    found = find_sensitive_fields(data)
    if found:
        raise SensitiveDataError(
            "Import refusé : champs sensibles détectés "
            f"({', '.join(sorted(set(found)))}). AI Investor ne traite ni ne stocke aucun "
            "identifiant, mot de passe, PIN, code 2FA, cookie, token ou coordonnée bancaire."
        )


def assert_no_sensitive_columns(columns: Iterable[str]) -> None:
    """Variante pour les en-têtes de fichiers CSV."""
    assert_no_sensitive_fields({c: None for c in columns})
