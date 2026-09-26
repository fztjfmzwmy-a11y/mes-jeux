"""Analyse du portefeuille — calculs purs, sans accès aux fournisseurs.

Principes :
- aucune donnée manquante n'est remplacée : un prix absent rend la valeur totale INCONNUE
  (seule la valeur partielle connue est donnée, clairement signalée) ;
- le prix de revient n'est jamais utilisé comme substitut du prix de marché ;
- pas de conversion de devise en V1 : une position dans une autre devise est non valorisée ;
- les métriques historiques du portefeuille supposent des quantités constantes : c'est une
  HYPOTHÈSE, affichée comme telle.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict

from ai_investor.config import RiskRules, Settings
from ai_investor.core.enums import AssetType, QualityLevel
from ai_investor.core.models import CashBalance, Position, PriceBar, Quote
from ai_investor.quant.indicators import annualized_volatility, drawdown, simple_returns, to_pct

HUNDRED = Decimal(100)
PCT = Decimal("0.01")

CASH_BUCKET = "Liquidités"
DIVERSIFIED_BUCKET = "Diversifié (ETF/fonds, détail indisponible)"
UNKNOWN_BUCKET = "Inconnu"


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"


class Alert(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    severity: Severity
    message: str
    symbol: str | None = None


class PositionAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    asset_type: AssetType
    currency: str
    sector: str | None
    region: str | None
    quantity: Decimal
    average_price: Decimal
    cost_basis: Decimal
    price: Decimal | None = None
    price_as_of: AwareDatetime | None = None
    price_source: str | None = None
    market_value: Decimal | None = None
    weight_percent: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    unrealized_pnl_percent: Decimal | None = None
    last_daily_move_percent: Decimal | None = None
    issues: tuple[str, ...] = ()


class Correlation(BaseModel):
    model_config = ConfigDict(frozen=True)

    a: str
    b: str
    coefficient: float
    observations: int


class PortfolioAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True)

    as_of: AwareDatetime
    base_currency: str
    valuation_complete: bool
    total_value: Decimal | None  # None si au moins une position n'est pas valorisable
    known_value: Decimal  # positions valorisées + liquidités en devise de base
    cash: Decimal
    cash_percent: Decimal | None
    invested_value: Decimal
    cost_basis_total: Decimal
    unrealized_pnl: Decimal | None
    unrealized_pnl_percent: Decimal | None
    positions: tuple[PositionAnalysis, ...]
    sector_exposure: dict[str, Decimal]
    region_exposure: dict[str, Decimal]
    currency_exposure: dict[str, Decimal]
    asset_type_exposure: dict[str, Decimal]
    hhi: Decimal | None
    effective_positions: Decimal | None
    largest_position: str | None
    largest_position_percent: Decimal | None
    etf_overlaps: tuple[tuple[str, ...], ...]
    correlations: tuple[Correlation, ...]
    history_days: int
    volatility_annual_percent: Decimal | None
    max_drawdown_percent: Decimal | None
    current_drawdown_percent: Decimal | None
    alerts: tuple[Alert, ...]
    missing_data: tuple[str, ...]
    assumptions: tuple[str, ...]
    data_quality: QualityLevel


def _pct(part: Decimal, whole: Decimal) -> Decimal:
    return (part / whole * HUNDRED).quantize(PCT)


def _exposure(values: Mapping[str, Decimal], total: Decimal) -> dict[str, Decimal]:
    if total <= 0:
        return {}
    return {k: _pct(v, total) for k, v in sorted(values.items(), key=lambda kv: -kv[1])}


def _sector_bucket(position: Position) -> str:
    if position.asset.sector:
        return position.asset.sector
    if position.asset.asset_type in (AssetType.ETF, AssetType.FUND):
        return DIVERSIFIED_BUCKET
    return UNKNOWN_BUCKET


def _closes(bars: Sequence[PriceBar], currency: str) -> dict[date, Decimal]:
    return {b.day: b.close for b in bars if b.currency == currency}


def analyze_portfolio(
    positions: Sequence[Position],
    cash: Sequence[CashBalance],
    quotes: Mapping[str, Quote | None],
    histories: Mapping[str, Sequence[PriceBar]],
    base_currency: str,
    now: datetime,
    settings: Settings,
    rules: RiskRules,
    unavailable: Mapping[str, str] | None = None,
) -> PortfolioAnalysis:
    """`unavailable` : symbole -> raison (ex. fournisseur indisponible) pour les prix absents."""
    unavailable = unavailable or {}
    max_age = timedelta(days=settings.MAX_DATA_AGE_DAYS)
    missing: list[str] = []
    assumptions: list[str] = []
    alerts: list[Alert] = []
    degraded = False  # qualité MEDIUM au mieux

    # --- Liquidités -------------------------------------------------------------------
    cash_base = Decimal(0)
    for balance in cash:
        if balance.currency == base_currency:
            cash_base += balance.amount
        else:
            missing.append(
                f"Liquidités {balance.amount} {balance.currency} non converties "
                f"(conversion vers {base_currency} non disponible)"
            )

    # --- Valorisation des positions ---------------------------------------------------
    drafts: list[dict[str, object]] = []
    valued: dict[str, Decimal] = {}
    for p in positions:
        sym = p.asset.symbol
        issues: list[str] = []
        quote = quotes.get(sym)
        price: Decimal | None = None
        if p.asset.currency != base_currency:
            issues.append(f"coté en {p.asset.currency} : conversion non disponible")
        elif quote is None:
            issues.append(unavailable.get(sym, "prix de marché indisponible"))
        elif quote.currency != p.asset.currency:
            issues.append(f"prix reçu en {quote.currency}, actif en {p.asset.currency}")
        else:
            price = quote.price
            if now - quote.as_of > max_age:
                issues.append(f"prix périmé (du {quote.as_of:%Y-%m-%d})")
                degraded = True
        if price is None:
            missing.append(f"{sym} : {issues[-1]}")
        value = p.quantity * price if price is not None else None
        if value is not None:
            valued[sym] = value
        pnl = value - p.cost_basis if value is not None else None
        drafts.append(
            {
                "symbol": sym,
                "name": p.asset.name,
                "asset_type": p.asset.asset_type,
                "currency": p.asset.currency,
                "sector": p.asset.sector,
                "region": p.asset.region,
                "quantity": p.quantity,
                "average_price": p.average_price,
                "cost_basis": p.cost_basis.quantize(PCT),
                "price": price,
                "price_as_of": quote.as_of if price is not None and quote else None,
                "price_source": quote.source.name if price is not None and quote else None,
                "market_value": value.quantize(PCT) if value is not None else None,
                "unrealized_pnl": pnl.quantize(PCT) if pnl is not None else None,
                "unrealized_pnl_percent": _pct(pnl, p.cost_basis) if pnl is not None else None,
                "issues": tuple(issues),
            }
        )

    complete = len(valued) == len(positions)
    invested = sum(valued.values(), Decimal(0))
    known_value = invested + cash_base
    total_value = known_value if complete else None
    if not complete:
        assumptions.append(
            "Valorisation partielle : poids et expositions calculés sur la seule partie "
            "valorisée du portefeuille, à titre indicatif."
        )

    # --- Historique : dernières variations, corrélations, risque du portefeuille ------
    closes = {
        p.asset.symbol: _closes(histories.get(p.asset.symbol, ()), p.asset.currency)
        for p in positions
    }
    for draft in drafts:
        series = closes[str(draft["symbol"])]
        days = sorted(series)
        if len(days) >= 2:
            prev, last = series[days[-2]], series[days[-1]]
            move = _pct(last - prev, prev)
            draft["last_daily_move_percent"] = move
            if abs(move) >= settings.ABNORMAL_DAILY_MOVE_PERCENT:
                alerts.append(
                    Alert(
                        code="ABNORMAL_MOVE",
                        severity=Severity.WARNING,
                        symbol=str(draft["symbol"]),
                        message=f"{draft['symbol']} : variation de {move} % le {days[-1]}",
                    )
                )

    min_days = settings.MIN_HISTORY_DAYS
    correlations: list[Correlation] = []
    symbols = [p.asset.symbol for p in positions]
    for i, a in enumerate(symbols):
        for b in symbols[i + 1 :]:
            common = sorted(set(closes[a]) & set(closes[b]))
            if len(common) < min_days + 1:
                continue
            ra = simple_returns([float(closes[a][d]) for d in common])
            rb = simple_returns([float(closes[b][d]) for d in common])
            try:
                rho = statistics.correlation(ra, rb)
            except statistics.StatisticsError:
                continue  # série constante : corrélation non définie
            correlations.append(
                Correlation(a=a, b=b, coefficient=round(rho, 4), observations=len(ra))
            )
            if rho >= float(settings.CORRELATION_ALERT_THRESHOLD):
                alerts.append(
                    Alert(
                        code="HIGH_CORRELATION",
                        severity=Severity.WARNING,
                        message=f"{a} et {b} très corrélés ({rho:.2f} sur {len(ra)} jours)",
                    )
                )

    volatility = max_dd = current_dd = None
    history_days = 0
    if positions:
        common_days = sorted(set.intersection(*(set(closes[s]) for s in symbols)))
        history_days = len(common_days)
        if history_days >= min_days + 1:
            series_values = [
                float(
                    sum((p.quantity * closes[p.asset.symbol][d] for p in positions), Decimal(0))
                    + cash_base
                )
                for d in common_days
            ]
            vol = annualized_volatility(simple_returns(series_values))
            volatility = to_pct(vol) if vol is not None else None
            dd = drawdown(series_values)
            if dd is not None:  # toujours vrai ici : la série est non vide
                max_dd, current_dd = to_pct(dd.maximum), to_pct(dd.current)
            assumptions.append(
                "Volatilité et drawdown calculés à quantités actuelles constantes sur "
                f"{history_days} jours communs (reconstitution, pas l'historique réel)."
            )
            if current_dd is not None and abs(current_dd) > rules.MAX_DRAWDOWN:
                alerts.append(
                    Alert(
                        code="DRAWDOWN_EXCEEDED",
                        severity=Severity.HIGH,
                        message=f"Drawdown actuel {current_dd} % au-delà de "
                        f"la limite de {rules.MAX_DRAWDOWN} %",
                    )
                )
            elif max_dd is not None and abs(max_dd) > rules.MAX_DRAWDOWN:
                alerts.append(
                    Alert(
                        code="PAST_DRAWDOWN_EXCEEDED",
                        severity=Severity.WARNING,
                        message=f"Drawdown maximal historique {max_dd} % au-delà "
                        f"de la limite de {rules.MAX_DRAWDOWN} %",
                    )
                )
        else:
            missing.append(
                f"Historique commun insuffisant ({history_days} jours, {min_days + 1} requis) : "
                "volatilité et drawdown non calculés"
            )
            degraded = True

    # --- Poids, expositions, concentration --------------------------------------------
    by_symbol = {p.asset.symbol: p for p in positions}
    sectors: dict[str, Decimal] = defaultdict(Decimal)
    regions: dict[str, Decimal] = defaultdict(Decimal)
    currencies: dict[str, Decimal] = defaultdict(Decimal)
    types: dict[str, Decimal] = defaultdict(Decimal)
    for sym, value in valued.items():
        p = by_symbol[sym]
        sectors[_sector_bucket(p)] += value
        regions[p.asset.region or UNKNOWN_BUCKET] += value
        currencies[p.asset.currency] += value
        types[p.asset.asset_type] += value
    if cash_base:
        for bucket in (sectors, regions, types):
            bucket[CASH_BUCKET] += cash_base
        currencies[base_currency] += cash_base

    for draft in drafts:
        value = valued.get(str(draft["symbol"]))
        if value is not None and known_value > 0:
            draft["weight_percent"] = _pct(value, known_value)

    hhi = effective = largest_pct = None
    largest = None
    if invested > 0:
        hhi = sum(((v / invested) ** 2 for v in valued.values()), Decimal(0)).quantize(
            Decimal("0.0001")
        )
        effective = (Decimal(1) / hhi).quantize(PCT) if hhi else None
        largest = max(valued, key=lambda s: valued[s])
        largest_pct = _pct(valued[largest], known_value)
        if hhi >= settings.CONCENTRATION_HHI_ALERT:
            alerts.append(
                Alert(
                    code="CONCENTRATED",
                    severity=Severity.WARNING,
                    message=f"Portefeuille concentré : équivalent à {effective} "
                    "positions de même poids",
                )
            )

    for draft in drafts:
        weight = draft.get("weight_percent")
        if isinstance(weight, Decimal) and weight > rules.MAX_POSITION_PERCENT:
            alerts.append(
                Alert(
                    code="POSITION_TOO_LARGE",
                    severity=Severity.HIGH,
                    symbol=str(draft["symbol"]),
                    message=f"{draft['symbol']} pèse {weight} % "
                    f"(limite {rules.MAX_POSITION_PERCENT} %)",
                )
            )
    sector_exposure = _exposure(sectors, known_value)
    for sector, weight in sector_exposure.items():
        if sector in (CASH_BUCKET, DIVERSIFIED_BUCKET, UNKNOWN_BUCKET):
            continue
        if weight > rules.MAX_SECTOR_EXPOSURE:
            alerts.append(
                Alert(
                    code="SECTOR_TOO_LARGE",
                    severity=Severity.HIGH,
                    message=f"Secteur {sector} : {weight} % (limite {rules.MAX_SECTOR_EXPOSURE} %)",
                )
            )
    if sector_exposure.get(UNKNOWN_BUCKET, Decimal(0)) > 0:
        degraded = True
        missing.append(f"Secteur inconnu pour {sector_exposure[UNKNOWN_BUCKET]} % du portefeuille")
    if sector_exposure.get(DIVERSIFIED_BUCKET):
        assumptions.append(
            "Composition des ETF/fonds non disponible : pas de vue par transparence."
        )

    cash_percent = _pct(cash_base, known_value) if known_value > 0 else None
    if cash_percent is not None and cash_percent < rules.MIN_CASH_PERCENT:
        alerts.append(
            Alert(
                code="LOW_CASH",
                severity=Severity.WARNING,
                message=f"Liquidités {cash_percent} % (minimum {rules.MIN_CASH_PERCENT} %)",
            )
        )

    # --- ETF en doublon, actifs hors règles --------------------------------------------
    by_index: dict[str, list[str]] = defaultdict(list)
    for p in positions:
        if p.asset.asset_type in (AssetType.ETF, AssetType.FUND) and p.asset.tracked_index:
            by_index[p.asset.tracked_index.strip().upper()].append(p.asset.symbol)
    overlaps = tuple(tuple(sorted(v)) for v in by_index.values() if len(v) > 1)
    for group in overlaps:
        alerts.append(
            Alert(
                code="ETF_OVERLAP",
                severity=Severity.WARNING,
                message=f"ETF répliquant le même indice : {', '.join(group)}",
            )
        )
    for p in positions:
        if not rules.is_asset_type_allowed(p.asset.asset_type):
            alerts.append(
                Alert(
                    code="ASSET_TYPE_NOT_ALLOWED",
                    severity=Severity.HIGH,
                    symbol=p.asset.symbol,
                    message=f"{p.asset.symbol} : type {p.asset.asset_type} non autorisé "
                    "par vos règles",
                )
            )
        if {p.asset.symbol, p.asset.isin or ""} & rules.FORBIDDEN_ASSETS:
            alerts.append(
                Alert(
                    code="FORBIDDEN_ASSET_HELD",
                    severity=Severity.HIGH,
                    symbol=p.asset.symbol,
                    message=f"{p.asset.symbol} figure dans vos actifs interdits",
                )
            )

    cost_total = sum((p.cost_basis for p in positions), Decimal(0))
    valued_cost = sum((by_symbol[s].cost_basis for s in valued), Decimal(0))
    pnl_total = (invested - valued_cost).quantize(PCT) if complete and positions else None

    if not positions and not cash_base:
        quality = QualityLevel.LOW
        missing.append("Portefeuille vide ou non valorisable")
    elif not complete:
        quality = QualityLevel.LOW
    elif degraded:
        quality = QualityLevel.MEDIUM
    else:
        quality = QualityLevel.HIGH

    return PortfolioAnalysis(
        as_of=now,
        base_currency=base_currency,
        valuation_complete=complete,
        total_value=total_value.quantize(PCT) if total_value is not None else None,
        known_value=known_value.quantize(PCT),
        cash=cash_base,
        cash_percent=cash_percent,
        invested_value=invested.quantize(PCT),
        cost_basis_total=cost_total.quantize(PCT),
        unrealized_pnl=pnl_total,
        unrealized_pnl_percent=_pct(pnl_total, valued_cost)
        if pnl_total is not None and valued_cost
        else None,
        positions=tuple(PositionAnalysis.model_validate(d) for d in drafts),
        sector_exposure=sector_exposure,
        region_exposure=_exposure(regions, known_value),
        currency_exposure=_exposure(currencies, known_value),
        asset_type_exposure=_exposure(types, known_value),
        hhi=hhi,
        effective_positions=effective,
        largest_position=largest,
        largest_position_percent=largest_pct,
        etf_overlaps=overlaps,
        correlations=tuple(correlations),
        history_days=history_days,
        volatility_annual_percent=volatility,
        max_drawdown_percent=max_dd,
        current_drawdown_percent=current_dd,
        alerts=tuple(alerts),
        missing_data=tuple(missing),
        assumptions=tuple(assumptions),
        data_quality=quality,
    )
