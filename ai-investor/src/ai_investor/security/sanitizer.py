"""Neutralisation du contenu externe (actualités, fichiers, champs texte).

Le contenu externe est une DONNÉE, jamais une instruction. Ce module :
- nettoie le texte (caractères de contrôle ou invisibles, balises HTML, longueur) ;
- détecte les tentatives d'injection (consignes adressées à l'IA, demandes d'ordre,
  d'identifiants…) afin de les SIGNALER — le texte n'est jamais exécuté ni obéi ;
- encadre le texte par des délimiteurs explicites si un modèle de langage devait un jour
  le lire (option désactivée en V1).

La détection est volontairement large : un faux positif rend seulement l'actualité
« suspecte » ; aucun comportement du système n'en dépend pour sa sécurité, qui repose
sur l'absence de capacité d'exécution.
"""

from __future__ import annotations

import html
import re
import unicodedata
from urllib.parse import urlparse

MAX_TEXT_LENGTH = 5000

_INVISIBLE = re.compile(r"[​-‏‪-‮⁠-⁤﻿]")
_TAGS = re.compile(r"<[^>]{0,500}>")
_SPACES = re.compile(r"\s+")

INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern, re.IGNORECASE))
    for name, pattern in (
        (
            "ignore_instructions",
            r"\b(ignore[rz]?|oublie[rz]?|disregard|forget)\b.{0,40}\b(instructions?|consignes?|"
            r"r[eè]gles?|rules|prompt|above|pr[eé]c[eé]dent)",
        ),
        (
            "role_override",
            r"\b(you are now|tu es (maintenant|d[ée]sormais)|act as|agis comme|"
            r"new instructions|nouvelles? instructions?|system prompt|prompt syst[eè]me)\b",
        ),
        (
            "fake_role_marker",
            r"(^|\s)(system|assistant|developer|syst[eè]me)\s*:|<\|?(system|im_start|im_end)\|?>|"
            r"\[/?(INST|SYS)\]|#{3,}\s*(system|instructions?)",
        ),
        (
            "order_request",
            r"\b(place[_ ]?order|passe[rz]? (un |l')?ordre|ex[eé]cute[rz]? (un |l')?ordre|"
            r"(buy|sell|ach[eè]te[rz]?|vends?|vendez) (now|imm[eé]diatement|tout|maintenant)|"
            r"transfer[_ ]money|withdraw[_ ]money|vire(r|z)? (l'argent|les fonds))\b",
        ),
        (
            "credential_request",
            r"\b(mot de passe|password|code pin|\bpin\b|2fa|code de v[eé]rification|"
            r"identifiants?|credentials?|token|cookie)\b.{0,40}\b(envoie|donne|send|share|"
            r"entre[rz]?|saisi[rz]?|provide|communique)|\b(envoie|envoy\w*|donne\w*|send|"
            r"share|communique\w*|transmet\w*|fourni\w*|indique\w*)\b.{0,40}"
            r"\b(mot de passe|password|pin|2fa|identifiants?|token|code)\b",
        ),
        (
            "override_risk",
            r"\b(d[ée]sactive[rz]?|contourne[rz]?|bypass|disable|override)\b.{0,40}"
            r"\b(risque|risk|r[eè]gles?|rules|s[eé]curit[eé]|security|limites?|limits?)\b",
        ),
    )
)


def clean_text(text: str, max_length: int = MAX_TEXT_LENGTH) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE.sub("", text)
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    text = html.unescape(_TAGS.sub(" ", text))
    text = _SPACES.sub(" ", text).strip()
    if len(text) > max_length:
        text = text[: max_length - 1].rstrip() + "…"
    return text


def detect_injection(text: str) -> tuple[str, ...]:
    """Noms des motifs d'injection détectés (après nettoyage, pour déjouer l'obfuscation)."""
    cleaned = clean_text(text, max_length=50_000)
    return tuple(name for name, pattern in INJECTION_PATTERNS if pattern.search(cleaned))


def safe_url(url: str | None) -> str | None:
    """Ne conserve qu'une URL http(s) avec un hôte ; tout le reste est écarté."""
    if not url:
        return None
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    return parsed.geturl()


def url_host(url: str | None) -> str | None:
    safe = safe_url(url)
    host = urlparse(safe).hostname if safe else None
    return host.lower() if host else None


BEGIN = "<<<DONNÉE_EXTERNE_NON_FIABLE>>>"
END = "<<<FIN_DONNÉE_EXTERNE>>>"


def wrap_untrusted(text: str) -> str:
    """Encadre un texte externe ; toute imitation des délimiteurs est neutralisée."""
    body = clean_text(text).replace("<<<", "‹‹‹").replace(">>>", "›››")
    return f"{BEGIN}\n{body}\n{END}"
