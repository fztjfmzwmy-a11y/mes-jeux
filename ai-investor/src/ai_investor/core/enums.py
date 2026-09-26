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


class SimulatedOperation(StrEnum):
    """Opérations du portefeuille virtuel (section 13)."""

    BUY = "BUY"  # achat d'une nouvelle position
    SELL = "SELL"  # vente totale
    REINFORCE = "REINFORCE"  # renforcement d'une position existante
    REDUCE = "REDUCE"  # réduction partielle
    HOLD = "HOLD"  # conservation (enregistrée, sans mouvement)
    WAIT = "WAIT"  # attente (enregistrée, sans mouvement)
    DEPOSIT = "DEPOSIT"  # apport de capital virtuel
    WITHDRAWAL = "WITHDRAWAL"  # retrait de capital virtuel (aucun argent réel)


MOVEMENT_OPERATIONS = frozenset(
    {
        SimulatedOperation.BUY,
        SimulatedOperation.SELL,
        SimulatedOperation.REINFORCE,
        SimulatedOperation.REDUCE,
    }
)


class BrokerOperation(StrEnum):
    """Types d'opérations lues dans un export de courtier (données historiques)."""

    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    INTEREST = "INTEREST"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    FEE = "FEE"
    TAX = "TAX"
    OTHER = "OTHER"


class AgentReportStatus(StrEnum):
    OK = "OK"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNAVAILABLE = "UNAVAILABLE"  # agent en erreur ou hors délai
    UNKNOWN = "UNKNOWN"  # « je ne sais pas »


class AgentVerdict(StrEnum):
    """Avis émis par un agent dans le vote (section 12)."""

    BUY = "BUY"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    SELL = "SELL"
    WAIT = "WAIT"
    APPROVED = "APPROVED"
    BLOCK = "BLOCK"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NO_OPINION = "NO_OPINION"


class RiskOutcome(StrEnum):
    PASS = "PASS"  # noqa: S105 — issue d'un contrôle, pas un mot de passe
    WARN = "WARN"
    BLOCK = "BLOCK"


class JournalEntryType(StrEnum):
    DECISION = "DECISION"  # décision simulée complète
    OUTCOME = "OUTCOME"  # résultat ultérieur, lié à une décision (ne la modifie pas)
    SECURITY_EVENT = "SECURITY_EVENT"  # tentative refusée (ordre réel, identifiants, injection…)
