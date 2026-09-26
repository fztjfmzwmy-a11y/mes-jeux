"""Le code ne doit contenir AUCUNE capacité d'exécution réelle.

Analyse statique de tout le paquet : noms de fonctions, méthodes, classes et imports.
"""

import ast
import inspect
import re
from pathlib import Path

import pytest

import ai_investor
from ai_investor.data import interfaces

SRC = Path(ai_investor.__file__).parent

FORBIDDEN_NAME = re.compile(
    r"(place|submit|send|execute|create|cancel)_?(real_?)?order"
    r"|transfer_?(money|funds|cash)|withdraw|wire_?transfer"
    r"|change_?account|login_?broker|broker_?login|authenticate_?broker",
    re.IGNORECASE,
)
# Modules réseau / navigateur interdits dans le paquet à ce stade (aucune connexion externe).
FORBIDDEN_IMPORTS = {
    "pytr",
    "ccxt",
    "alpaca",
    "ib_insync",
    "selenium",
    "playwright",
    "websockets",
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "socket",
}


def _python_files():
    return sorted(SRC.rglob("*.py"))


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: str(p.relative_to(SRC)))
def test_no_order_execution_symbols(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and FORBIDDEN_NAME.search(node.name)
    ]
    assert not offenders, f"Symboles d'exécution interdits dans {path}: {offenders}"


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: str(p.relative_to(SRC)))
def test_no_network_or_broker_imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not imported & FORBIDDEN_IMPORTS, f"{path}: {imported & FORBIDDEN_IMPORTS}"


PROVIDER_CLASSES = [
    interfaces.PortfolioDataProvider,
    interfaces.MarketDataProvider,
    interfaces.NewsDataProvider,
    interfaces.MacroDataProvider,
    interfaces.BrokerDataProvider,
]


@pytest.mark.parametrize("cls", PROVIDER_CLASSES, ids=lambda c: c.__name__)
def test_provider_interfaces_are_read_only(cls):
    public = [
        name for name, _ in inspect.getmembers(cls) if not name.startswith("_") and name != "info"
    ]
    assert public, cls
    assert all(name.startswith("get_") for name in public), public


def test_provider_cannot_require_personal_credentials():
    from ai_investor.core.enums import DataReliability

    with pytest.raises(ValueError, match="identifiants"):
        interfaces.ProviderInfo(
            name="broker-login",
            reliability=DataReliability.THIRD_PARTY,
            requires_personal_credentials=True,
        )
