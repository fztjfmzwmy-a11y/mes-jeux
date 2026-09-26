"""Exceptions métier. Une erreur explicite vaut mieux qu'une valeur inventée."""


class AIInvestorError(Exception):
    """Base de toutes les erreurs du projet."""


class ConfigurationError(AIInvestorError):
    """Configuration invalide ou dangereuse."""


class ForbiddenActionError(AIInvestorError):
    """Tentative d'action interdite (ordre réel, transfert, retrait, modification de compte)."""


class PermissionDeniedError(AIInvestorError):
    """Un agent tente d'utiliser une permission qu'il ne possède pas."""


class SensitiveDataError(AIInvestorError):
    """Une donnée d'entrée contient un identifiant ou un secret qui ne doit pas être traité."""


class InsufficientDataError(AIInvestorError):
    """Données manquantes : l'analyse doit répondre « DONNÉES INSUFFISANTES »."""


class StaleDataError(AIInvestorError):
    """Données trop anciennes pour fonder une analyse."""


class ProviderUnavailableError(AIInvestorError):
    """Fournisseur de données indisponible."""
