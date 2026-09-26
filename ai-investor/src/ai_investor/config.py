"""Chargement et validation de la configuration.

Les valeurs par défaut (config/*.default.yaml) sont des garde-fous techniques et
NON des recommandations financières personnalisées. Un fichier *.local.yaml peut
les surcharger ; toute valeur incohérente ou dangereuse est refusée.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from ai_investor.core.enums import COMPLEX_ASSET_TYPES, LEVERAGED_ASSET_TYPES, AssetType
from ai_investor.core.errors import ConfigurationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"

Percent = Decimal


class RiskRules(BaseModel):
    """Règles de risque appliquées par le Risk Manager. Pourcentages en % (10 = 10 %)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    MAX_TRANSACTION_AMOUNT: Decimal = Field(gt=0)
    MAX_POSITION_PERCENT: Percent = Field(gt=0, le=100)
    MAX_SECTOR_EXPOSURE: Percent = Field(gt=0, le=100)
    MIN_CASH_PERCENT: Percent = Field(ge=0, lt=100)
    MAX_DRAWDOWN: Percent = Field(gt=0, le=100)
    ALLOW_LEVERAGE: bool = False
    ALLOW_COMPLEX_PRODUCTS: bool = False
    ALLOWED_ASSET_TYPES: frozenset[AssetType]
    BLOCKED_ASSET_TYPES: frozenset[AssetType] = frozenset()
    FORBIDDEN_ASSETS: frozenset[str] = frozenset()

    @field_validator("FORBIDDEN_ASSETS", mode="before")
    @classmethod
    def _normalize_assets(cls, value: Any) -> Any:
        if isinstance(value, list | tuple | set | frozenset):
            return frozenset(str(v).strip().upper() for v in value)
        return value

    @model_validator(mode="after")
    def _check_consistency(self) -> RiskRules:
        overlap = self.ALLOWED_ASSET_TYPES & self.BLOCKED_ASSET_TYPES
        if overlap:
            names = ", ".join(sorted(overlap))
            raise ValueError(f"Types d'actifs à la fois autorisés et bloqués : {names}")
        if not self.ALLOW_LEVERAGE and self.ALLOWED_ASSET_TYPES & LEVERAGED_ASSET_TYPES:
            raise ValueError("Actif à effet de levier autorisé alors que ALLOW_LEVERAGE = false")
        if not self.ALLOW_COMPLEX_PRODUCTS and self.ALLOWED_ASSET_TYPES & COMPLEX_ASSET_TYPES:
            raise ValueError("Produit complexe autorisé alors que ALLOW_COMPLEX_PRODUCTS = false")
        if self.MAX_POSITION_PERCENT + self.MIN_CASH_PERCENT > 100:
            raise ValueError("MAX_POSITION_PERCENT + MIN_CASH_PERCENT dépasse 100 %")
        return self

    def is_asset_type_allowed(self, asset_type: AssetType) -> bool:
        if asset_type in self.BLOCKED_ASSET_TYPES or asset_type not in self.ALLOWED_ASSET_TYPES:
            return False
        if asset_type in LEVERAGED_ASSET_TYPES and not self.ALLOW_LEVERAGE:
            return False
        return not (asset_type in COMPLEX_ASSET_TYPES and not self.ALLOW_COMPLEX_PRODUCTS)


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    SIMULATION_ONLY: Literal[True] = True
    BASE_CURRENCY: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    DEFAULT_INVESTMENT_HORIZON_YEARS: int = Field(default=5, ge=0, le=50)
    HOST: str = "127.0.0.1"
    PORT: int = Field(default=8000, ge=1, le=65535)
    DATABASE_URL: str = "sqlite:///data/ai_investor.db"
    MAX_DATA_AGE_DAYS: int = Field(default=3, ge=0)
    LLM_PROVIDER: Literal["none", "ollama", "anthropic"] = "none"
    SIMULATION_INITIAL_CAPITAL: Decimal = Field(default=Decimal("10000"), ge=0)
    SIMULATION_FEE_FIXED: Decimal = Field(default=Decimal("1"), ge=0)
    SIMULATION_FEE_PERCENT: Decimal = Field(default=Decimal("0"), ge=0, le=10)
    ABNORMAL_DAILY_MOVE_PERCENT: Decimal = Field(default=Decimal("8"), gt=0, le=100)
    CORRELATION_ALERT_THRESHOLD: Decimal = Field(default=Decimal("0.8"), gt=0, le=1)
    CONCENTRATION_HHI_ALERT: Decimal = Field(default=Decimal("0.25"), gt=0, le=1)
    MIN_HISTORY_DAYS: int = Field(default=20, ge=2)

    @field_validator("SIMULATION_ONLY", mode="before")
    @classmethod
    def _simulation_only(cls, value: Any) -> Any:
        if value is not True:
            raise ValueError(
                "SIMULATION_ONLY doit rester true : la phase 1 n'autorise aucune exécution réelle."
            )
        return value


class AppConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    settings: Settings
    risk_rules: RiskRules


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        content = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationError(f"Lecture impossible de {path}: {exc}") from exc
    if content is None:
        return {}
    if not isinstance(content, dict):
        raise ConfigurationError(f"{path} doit contenir un dictionnaire YAML")
    return content


def _merged(default: Path, override: Path | None) -> dict[str, Any]:
    data = _read_yaml(default)
    if override is not None and override.exists():
        data.update(_read_yaml(override))
    return data


def _override_path(env_var: str, explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit
    value = os.environ.get(env_var)
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_config(
    settings_file: Path | None = None,
    risk_rules_file: Path | None = None,
    config_dir: Path = CONFIG_DIR,
) -> AppConfig:
    """Charge les valeurs par défaut puis les surcharges locales, et valide l'ensemble."""
    settings_data = _merged(
        config_dir / "settings.default.yaml",
        _override_path("AI_INVESTOR_SETTINGS_FILE", settings_file),
    )
    rules_data = _merged(
        config_dir / "risk_rules.default.yaml",
        _override_path("AI_INVESTOR_RISK_RULES_FILE", risk_rules_file),
    )
    try:
        return AppConfig(
            settings=Settings.model_validate(settings_data),
            risk_rules=RiskRules.model_validate(rules_data),
        )
    except ValidationError as exc:
        raise ConfigurationError(f"Configuration invalide :\n{exc}") from exc
