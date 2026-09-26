"""Lecture macroéconomique et scénarios — fonctions pures.

Principes :
- chaque lecture découle d'une règle explicite, affichée avec le résultat ;
- trois scénarios sont TOUJOURS produits (central, favorable, défavorable), sans
  probabilité attribuée : ils servent à tester la robustesse du portefeuille, pas à prévoir ;
- un indicateur absent reste absent ; un indicateur ancien est signalé.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from ai_investor.core.enums import QualityLevel
from ai_investor.core.models import MacroObservation


class Category(StrEnum):
    INFLATION = "INFLATION"
    POLICY_RATE = "POLICY_RATE"
    BOND_10Y = "BOND_10Y"
    GROWTH = "GROWTH"
    UNEMPLOYMENT = "UNEMPLOYMENT"


@dataclass(frozen=True)
class IndicatorSpec:
    category: Category
    code: str
    label: str
    stale_after_days: int


# Codes par défaut (zone euro). Remplaçables via le paramètre `indicators` de la demande.
DEFAULT_INDICATORS: tuple[IndicatorSpec, ...] = (
    IndicatorSpec(Category.INFLATION, "EA_HICP_YOY", "Inflation IPCH zone euro (an/an)", 75),
    # Un taux directeur reste valable tant qu'il n'est pas modifié.
    IndicatorSpec(Category.POLICY_RATE, "ECB_DEPOSIT_RATE", "Taux de dépôt BCE", 400),
    IndicatorSpec(Category.BOND_10Y, "EA_10Y_YIELD", "Taux souverain 10 ans", 45),
    IndicatorSpec(Category.GROWTH, "EA_GDP_YOY", "Croissance du PIB zone euro (an/an)", 200),
    IndicatorSpec(Category.UNEMPLOYMENT, "EA_UNEMPLOYMENT", "Taux de chômage zone euro", 100),
)

NO_PROBABILITY = (
    "Aucune probabilité n'est attribuée : ces scénarios servent à tester la robustesse du "
    "portefeuille, pas à prévoir l'avenir."
)


class Direction(StrEnum):
    RISING = "EN HAUSSE"
    FALLING = "EN BAISSE"
    STABLE = "STABLE"
    UNKNOWN = "INCONNUE"


class IndicatorReading(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: Category
    code: str
    label: str
    value: Decimal
    unit: str
    period: date
    source: str
    observations: int
    change_3m: Decimal | None
    change_12m: Decimal | None
    direction: Direction
    stale: bool


class Signal(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    value: str
    rule: str
    stress: bool = False


class Scenario(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str  # CENTRAL / FAVORABLE / DÉFAVORABLE
    title: str
    narrative: str
    conditions: tuple[str, ...]
    possible_effects: dict[str, str]
    portfolio_notes: tuple[str, ...]


class MacroAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    as_of: datetime
    readings: tuple[IndicatorReading, ...]
    missing: tuple[str, ...]
    signals: tuple[Signal, ...]
    stress_count: int
    scenarios: tuple[Scenario, ...]
    generic_scenarios: bool
    data_quality: QualityLevel


def _value_before(series: Sequence[MacroObservation], target: date) -> Decimal | None:
    result = None
    for obs in series:
        if obs.period > target:
            break
        result = obs.value
    return result


def read_indicator(
    spec: IndicatorSpec,
    series: Sequence[MacroObservation],
    now: datetime,
    stable_threshold: Decimal,
) -> IndicatorReading | None:
    series = sorted((o for o in series if o.period <= now.date()), key=lambda o: o.period)
    if not series:
        return None
    last = series[-1]
    before_3m = _value_before(series, last.period - timedelta(days=85))
    before_12m = _value_before(series, last.period - timedelta(days=360))
    change_3m = last.value - before_3m if before_3m is not None else None
    change_12m = last.value - before_12m if before_12m is not None else None
    reference = change_12m if change_12m is not None else change_3m
    if reference is None:
        direction = Direction.UNKNOWN
    elif reference > stable_threshold:
        direction = Direction.RISING
    elif reference < -stable_threshold:
        direction = Direction.FALLING
    else:
        direction = Direction.STABLE
    return IndicatorReading(
        category=spec.category,
        code=spec.code,
        label=spec.label,
        value=last.value,
        unit=last.unit,
        period=last.period,
        source=last.source.name,
        observations=len(series),
        change_3m=change_3m,
        change_12m=change_12m,
        direction=direction,
        stale=(now.date() - last.period).days > spec.stale_after_days,
    )


def build_signals(
    r: Mapping[Category, IndicatorReading], target: Decimal, threshold: Decimal
) -> list[Signal]:
    signals: list[Signal] = []
    infl = r.get(Category.INFLATION)
    rate = r.get(Category.POLICY_RATE)
    bond = r.get(Category.BOND_10Y)
    gdp = r.get(Category.GROWTH)
    unemp = r.get(Category.UNEMPLOYMENT)
    if infl:
        level = (
            "ÉLEVÉE"
            if infl.value > target + 1
            else "BASSE"
            if infl.value < target - 1
            else "PROCHE DE LA CIBLE"
        )
        signals.append(
            Signal(
                name="Inflation",
                value=f"{level} ({infl.value} %)",
                rule=f"élevée > {target + 1} %, basse < {target - 1} %",
            )
        )
    if rate:
        stance = {Direction.RISING: "RESSERREMENT", Direction.FALLING: "ASSOUPLISSEMENT"}.get(
            rate.direction, "STABLE" if rate.direction == Direction.STABLE else "INCONNUE"
        )
        signals.append(
            Signal(
                name="Politique monétaire",
                value=stance,
                rule=f"variation du taux directeur sur 12 mois vs ±{threshold} pt",
            )
        )
    if rate and infl:
        real = rate.value - infl.value
        signals.append(
            Signal(
                name="Taux réel (directeur - inflation)",
                value=f"{real} pt",
                rule="positif = politique restrictive en termes réels",
            )
        )
    if bond and rate:
        spread = bond.value - rate.value
        inverted = spread < 0
        signals.append(
            Signal(
                name="Pente (10 ans - taux directeur)",
                value=f"{'INVERSÉE' if inverted else 'POSITIVE'} ({spread} pt)",
                rule="une courbe inversée a souvent précédé des ralentissements, sans certitude",
                stress=inverted,
            )
        )
    if gdp:
        state = "CONTRACTION" if gdp.value < 0 else "FAIBLE" if gdp.value < 1 else "MODÉRÉE+"
        signals.append(
            Signal(
                name="Croissance",
                value=f"{state} ({gdp.value} %)",
                rule="contraction < 0 %, faible < 1 %",
                stress=gdp.value < 0,
            )
        )
    if unemp:
        worse = unemp.direction == Direction.RISING
        signals.append(
            Signal(
                name="Emploi",
                value="SE DÉGRADE"
                if worse
                else "S'AMÉLIORE"
                if unemp.direction == Direction.FALLING
                else str(unemp.direction),
                rule=f"variation du chômage sur 12 mois vs ±{threshold} pt",
                stress=worse,
            )
        )
    if infl and rate and infl.value > target + 1 and rate.direction == Direction.RISING:
        signals.append(
            Signal(
                name="Inflation + resserrement",
                value="OUI",
                rule="inflation élevée et taux directeur en hausse",
                stress=True,
            )
        )
    return signals


def _equity_share(exposures: Mapping[str, Any]) -> Decimal | None:
    types = exposures.get("asset_types")
    if not isinstance(types, Mapping):
        return None
    try:
        return sum((Decimal(str(types.get(k, 0))) for k in ("STOCK", "ETF", "FUND")), Decimal(0))
    except ArithmeticError:
        return None


def build_scenarios(
    r: Mapping[Category, IndicatorReading],
    signals: Sequence[Signal],
    target: Decimal,
    exposures: Mapping[str, Any] | None,
    generic: bool,
) -> tuple[Scenario, ...]:
    infl = r.get(Category.INFLATION)
    gdp = r.get(Category.GROWTH)
    high_inflation = infl is not None and infl.value > target + 1
    weak_growth = gdp is not None and gdp.value < 1
    notes: list[str] = []
    equity = _equity_share(exposures or {})
    cash = None
    if exposures and isinstance(exposures.get("asset_types"), Mapping):
        cash = exposures["asset_types"].get("CASH")
    if equity is not None:
        notes.append(
            f"{equity} % du portefeuille en actions/ETF/fonds (ETF et fonds supposés "
            "actions : composition non vérifiée)"
        )
    if cash is not None:
        notes.append(f"{cash} % en liquidités")
    portfolio_notes = tuple(notes) or (
        "Expositions du portefeuille non fournies : impact non chiffré",
    )

    current = "; ".join(f"{s.name} : {s.value}" for s in signals) or "situation non mesurée"
    central = Scenario(
        kind="CENTRAL",
        title="Prolongation de la situation actuelle",
        narrative=(
            "Les tendances observées se prolongent sans rupture. " + current
            if not generic
            else "Données insuffisantes : scénario générique de continuité."
        ),
        conditions=("Indicateurs proches de leurs dernières valeurs dans les prochains mois",),
        possible_effects={
            "actions": "pourraient suivre les résultats des entreprises, sans signal macro fort",
            "obligations": "rendements proches des niveaux actuels",
            "liquidités": "rémunération proche du taux directeur actuel",
        },
        portfolio_notes=portfolio_notes,
    )
    favorable = Scenario(
        kind="FAVORABLE",
        title="Désinflation et stabilisation de la croissance",
        narrative="L'inflation converge vers la cible, la croissance se stabilise ou accélère, "
        "la banque centrale peut assouplir progressivement.",
        conditions=(
            f"Inflation qui se rapproche de {target} %",
            "Croissance stable ou en hausse",
            "Chômage stable ou en baisse",
        ),
        possible_effects={
            "actions": "pourraient bénéficier de taux plus bas et d'une croissance stable",
            "obligations": "pourraient s'apprécier si les taux longs baissent",
            "liquidités": "rémunération qui pourrait diminuer",
        },
        portfolio_notes=portfolio_notes,
    )
    if high_inflation:
        adverse_title = "Inflation persistante et taux durablement élevés"
        adverse_story = (
            "L'inflation reste au-dessus de la cible, la banque centrale maintient "
            "ou relève ses taux, la croissance ralentit."
        )
        adverse_conditions = (
            "Inflation qui ne reflue pas",
            "Taux directeurs en hausse",
            "Taux longs en hausse",
        )
    else:
        adverse_title = "Ralentissement marqué / récession"
        adverse_story = (
            "La croissance devient négative, le chômage augmente et les résultats "
            "des entreprises reculent." + (" La croissance est déjà faible." if weak_growth else "")
        )
        adverse_conditions = (
            "PIB en contraction",
            "Chômage en hausse",
            "Courbe des taux inversée ou en ré-pentification brutale",
        )
    adverse = Scenario(
        kind="DÉFAVORABLE",
        title=adverse_title,
        narrative=adverse_story,
        conditions=adverse_conditions,
        possible_effects={
            "actions": "pourraient baisser fortement (drawdowns historiques de 30 % ou plus "
            "observés lors de récessions)",
            "obligations": "pourraient baisser si l'inflation persiste, ou monter en récession "
            "désinflationniste",
            "liquidités": "préservent le capital nominal, pas le pouvoir d'achat",
        },
        portfolio_notes=portfolio_notes,
    )
    return central, favorable, adverse


def analyze_macro(
    series_by_category: Mapping[Category, Sequence[MacroObservation]],
    specs: Sequence[IndicatorSpec],
    now: datetime,
    target: Decimal,
    threshold: Decimal,
    exposures: Mapping[str, Any] | None = None,
    unavailable: Mapping[Category, str] | None = None,
) -> MacroAnalysis:
    unavailable = unavailable or {}
    readings: dict[Category, IndicatorReading] = {}
    missing: list[str] = []
    for spec in specs:
        reading = read_indicator(spec, series_by_category.get(spec.category, ()), now, threshold)
        if reading is None:
            reason = unavailable.get(spec.category, "aucune donnée")
            missing.append(f"{spec.label} ({spec.code}) : {reason}")
            continue
        readings[spec.category] = reading
        if reading.stale:
            missing.append(f"{spec.label} : dernière donnée du {reading.period} (ancienne)")
    signals = build_signals(readings, target, threshold)
    available = len(readings)
    stale = any(r.stale for r in readings.values())
    generic = available < 3
    if generic:
        quality = QualityLevel.LOW
    elif available < len(specs) or stale:
        quality = QualityLevel.MEDIUM
    else:
        quality = QualityLevel.HIGH
    return MacroAnalysis(
        as_of=now,
        readings=tuple(readings.values()),
        missing=tuple(missing),
        signals=tuple(signals),
        stress_count=sum(1 for s in signals if s.stress),
        scenarios=build_scenarios(readings, signals, target, exposures, generic),
        generic_scenarios=generic,
        data_quality=quality,
    )
