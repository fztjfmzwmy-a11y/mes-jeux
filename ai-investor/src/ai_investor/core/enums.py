"""Vocabulaire commun à tous les agents."""

from enum import StrEnum


class Action(StrEnum):
    """Actions qu'un agent peut proposer. Toujours simulées."""

    BUY = "BUY"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    SELL = "SELL"
    WAIT = "WAIT"


class DecisionStatus(StrEnum):
    """Statut d'une proposition. Seul APPROVED autorise une transaction SIMULÉE."""

    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    CONTRADICTORY = "CONTRADICTORY"
    RISK_TOO_HIGH = "RISK_TOO_HIGH"
    UNKNOWN = "UNKNOWN"


# Formulations affichées à l'utilisateur : le système doit pouvoir dire « je ne sais pas ».
STATUS_LABELS_FR: dict[DecisionStatus, str] = {
    DecisionStatus.APPROVED: "VALIDÉ (SIMULATION)",
    DecisionStatus.BLOCKED: "BLOQUÉ",
    DecisionStatus.REVIEW_REQUIRED: "REVIEW REQUIRED",
    DecisionStatus.INSUFFICIENT_DATA: "DONNÉES INSUFFISANTES",
    DecisionStatus.CONTRADICTORY: "ANALYSES CONTRADICTOIRES",
    DecisionStatus.RISK_TOO_HIGH: "RISQUE TROP ÉLEVÉ",
    DecisionStatus.UNKNOWN: "JE NE SAIS PAS",
}


class QualityLevel(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AssetType(StrEnum):
    STOCK = "STOCK"
    ETF = "ETF"
    BOND = "BOND"
    FUND = "FUND"
    CASH = "CASH"
    CRYPTO = "CRYPTO"
    LEVERAGED_ETF = "LEVERAGED_ETF"
    DERIVATIVE = "DERIVATIVE"
    WARRANT = "WARRANT"
    CFD = "CFD"
    KNOCK_OUT = "KNOCK_OUT"


LEVERAGED_ASSET_TYPES = frozenset({AssetType.LEVERAGED_ETF, AssetType.CFD, AssetType.KNOCK_OUT})
COMPLEX_ASSET_TYPES = frozenset(
    {AssetType.DERIVATIVE, AssetType.WARRANT, AssetType.CFD, AssetType.KNOCK_OUT}
)


class DataReliability(StrEnum):
    """Fiabilité d'une source de données."""

    OFFICIAL = "OFFICIAL"  # banque centrale, institut statistique, relevé du courtier
    USER_PROVIDED = "USER_PROVIDED"  # fichier importé ou saisie manuelle
    THIRD_PARTY = "THIRD_PARTY"  # fournisseur de données tiers
    UNVERIFIED = "UNVERIFIED"  # actualité non recoupée, source inconnue
    SIMULATED = "SIMULATED"  # données fictives de test
