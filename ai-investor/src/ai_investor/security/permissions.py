"""Modèle de permissions des agents.

Principe : les actions dangereuses ne sont PAS des permissions désactivées, elles
n'existent pas dans l'énumération `Permission`. Il est donc impossible de les accorder,
par configuration ou par instruction. Toute demande qui les mentionne est refusée et
doit être journalisée par l'appelant.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from enum import StrEnum
from types import MappingProxyType

from ai_investor.core.errors import ForbiddenActionError, PermissionDeniedError


class Permission(StrEnum):
    READ_PORTFOLIO = "READ_PORTFOLIO"
    READ_MARKET = "READ_MARKET"
    READ_NEWS = "READ_NEWS"
    RUN_ANALYSIS = "RUN_ANALYSIS"
    RUN_SIMULATION = "RUN_SIMULATION"


# Actions interdites en toutes circonstances. Volontairement hors de l'énumération.
FORBIDDEN_ACTIONS: frozenset[str] = frozenset(
    {"PLACE_ORDER", "TRANSFER_MONEY", "WITHDRAW_MONEY", "CHANGE_ACCOUNT_SETTINGS"}
)


class AgentRole(StrEnum):
    DIRECTOR = "DIRECTOR"
    PORTFOLIO = "PORTFOLIO"
    MARKET = "MARKET"
    MACRO = "MACRO"
    NEWS = "NEWS"
    QUANT = "QUANT"
    RISK_MANAGER = "RISK_MANAGER"
    STRATEGIST = "STRATEGIST"
    DEVILS_ADVOCATE = "DEVILS_ADVOCATE"
    FINAL_REVIEW = "FINAL_REVIEW"


_P = Permission
_ALL_READ = frozenset({_P.READ_PORTFOLIO, _P.READ_MARKET, _P.READ_NEWS, _P.RUN_ANALYSIS})

# Permissions fixées dans le code (non configurables) : principe du moindre privilège.
AGENT_PERMISSIONS: Mapping[AgentRole, frozenset[Permission]] = MappingProxyType(
    {
        AgentRole.DIRECTOR: _ALL_READ,
        AgentRole.PORTFOLIO: frozenset({_P.READ_PORTFOLIO, _P.READ_MARKET, _P.RUN_ANALYSIS}),
        AgentRole.MARKET: frozenset({_P.READ_MARKET, _P.RUN_ANALYSIS}),
        AgentRole.MACRO: frozenset({_P.READ_MARKET, _P.RUN_ANALYSIS}),
        AgentRole.NEWS: frozenset({_P.READ_NEWS, _P.RUN_ANALYSIS}),
        AgentRole.QUANT: frozenset({_P.READ_MARKET, _P.RUN_ANALYSIS, _P.RUN_SIMULATION}),
        AgentRole.RISK_MANAGER: frozenset({_P.READ_PORTFOLIO, _P.READ_MARKET, _P.RUN_ANALYSIS}),
        AgentRole.STRATEGIST: _ALL_READ | {_P.RUN_SIMULATION},
        AgentRole.DEVILS_ADVOCATE: _ALL_READ,
        AgentRole.FINAL_REVIEW: _ALL_READ,
    }
)


def _normalize(name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", name.strip().upper()).strip("_")


def is_forbidden(name: str) -> bool:
    return _normalize(name) in FORBIDDEN_ACTIONS


def parse_permission(name: str) -> Permission:
    """Convertit un nom en permission. Refuse les actions interdites et les noms inconnus."""
    normalized = _normalize(name)
    if normalized in FORBIDDEN_ACTIONS:
        raise ForbiddenActionError(
            f"Action interdite : {normalized}. AI Investor fonctionne en simulation uniquement "
            "et ne peut pas passer d'ordre, transférer, retirer de l'argent ni modifier un compte."
        )
    try:
        return Permission(normalized)
    except ValueError:
        raise PermissionDeniedError(f"Permission inconnue : {name!r}") from None


def parse_permissions(names: Iterable[str]) -> frozenset[Permission]:
    return frozenset(parse_permission(n) for n in names)


def permissions_for(role: AgentRole) -> frozenset[Permission]:
    return AGENT_PERMISSIONS[role]


def require(role: AgentRole, requested: str | Permission) -> Permission:
    """Vérifie qu'un agent possède la permission demandée ; lève une erreur sinon.

    Aucune instruction (utilisateur, actualité, fichier, autre agent) ne peut élargir
    les permissions : elles ne dépendent que du rôle.
    """
    permission = parse_permission(str(requested))
    if permission not in AGENT_PERMISSIONS[role]:
        raise PermissionDeniedError(f"L'agent {role} n'a pas la permission {permission}.")
    return permission
