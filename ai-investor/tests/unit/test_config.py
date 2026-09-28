from decimal import Decimal
from pathlib import Path

import pytest

from ai_investor.config import load_config
from ai_investor.core.enums import AssetType
from ai_investor.core.errors import ConfigurationError


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_defaults_load():
    cfg = load_config()
    assert cfg.settings.SIMULATION_ONLY is True
    assert cfg.settings.BASE_CURRENCY == "EUR"
    assert cfg.settings.HOST == "127.0.0.1"
    assert cfg.settings.LLM_PROVIDER == "none"
    rules = cfg.risk_rules
    assert Decimal("1000") == rules.MAX_TRANSACTION_AMOUNT
    assert not rules.ALLOW_LEVERAGE and not rules.ALLOW_COMPLEX_PRODUCTS


def test_local_override_is_applied(tmp_path):
    override = _write(tmp_path, "r.yaml", "MAX_TRANSACTION_AMOUNT: 250\nFORBIDDEN_assets: []\n")
    with pytest.raises(ConfigurationError):  # clé inconnue refusée (faute de frappe)
        load_config(risk_rules_file=override)
    override = _write(tmp_path, "r.yaml", "MAX_TRANSACTION_AMOUNT: 250\nFORBIDDEN_ASSETS: [abc]\n")
    rules = load_config(risk_rules_file=override).risk_rules
    assert Decimal("250") == rules.MAX_TRANSACTION_AMOUNT
    assert frozenset({"ABC"}) == rules.FORBIDDEN_ASSETS


def test_simulation_only_cannot_be_disabled(tmp_path):
    override = _write(tmp_path, "s.yaml", "SIMULATION_ONLY: false\n")
    with pytest.raises(ConfigurationError, match="SIMULATION_ONLY"):
        load_config(settings_file=override)


@pytest.mark.parametrize(
    "content",
    [
        "MAX_POSITION_PERCENT: 150\n",
        "MAX_TRANSACTION_AMOUNT: -5\n",
        "MIN_CASH_PERCENT: 100\n",
        "MAX_POSITION_PERCENT: 60\nMIN_CASH_PERCENT: 50\n",
        "ALLOWED_ASSET_TYPES: [STOCK, CRYPTO]\n",  # CRYPTO est aussi bloqué par défaut
        "ALLOWED_ASSET_TYPES: [STOCK, CFD]\nBLOCKED_ASSET_TYPES: []\n",  # levier interdit
        "ALLOWED_ASSET_TYPES: [STOCK, WARRANT]\nBLOCKED_ASSET_TYPES: []\n",  # produit complexe
        "ALLOWED_ASSET_TYPES: [STOCK, NOT_A_TYPE]\n",
    ],
)
def test_invalid_risk_rules_rejected(tmp_path, content):
    with pytest.raises(ConfigurationError):
        load_config(risk_rules_file=_write(tmp_path, "r.yaml", content))


def test_malformed_yaml_rejected(tmp_path):
    with pytest.raises(ConfigurationError):
        load_config(risk_rules_file=_write(tmp_path, "r.yaml", "- juste\n- une liste\n"))


def test_asset_type_check():
    rules = load_config().risk_rules
    assert rules.is_asset_type_allowed(AssetType.ETF)
    assert not rules.is_asset_type_allowed(AssetType.CFD)
    assert not rules.is_asset_type_allowed(AssetType.CRYPTO)


def test_config_is_immutable():
    cfg = load_config()
    with pytest.raises(Exception):  # noqa: B017 — pydantic ValidationError (frozen)
        cfg.risk_rules.MAX_TRANSACTION_AMOUNT = Decimal("1000000")  # type: ignore[misc]


def test_default_rules_carry_non_advice_disclaimer():
    text = (Path(__file__).parents[2] / "config" / "risk_rules.default.yaml").read_text("utf-8")
    assert "PAS une recommandation financière" in text
