from datetime import date
from decimal import Decimal as D

import pytest

from ai_investor.core.errors import SensitiveDataError
from ai_investor.data.importers.positions import PositionImportError
from ai_investor.data.providers.csv_prices import CsvMarketDataProvider, parse_price_csv
from tests.helpers import SRC


def test_csv_price_provider(tmp_path):
    path = tmp_path / "prix.csv"
    path.write_text(
        "symbol;day;close;currency\ncw8;2026-09-24;500,5;EUR\nCW8;2026-09-25;502;EUR\n",
        encoding="utf-8",
    )
    provider = CsvMarketDataProvider(path)
    q = provider.get_latest_price("CW8")
    assert q.price == D(502) and q.as_of.date() == date(2026, 9, 25)
    assert len(provider.get_price_history("CW8", date(2026, 1, 1), date(2026, 12, 31))) == 2
    assert provider.get_latest_price("UNKNOWN") is None


@pytest.mark.parametrize(
    "line",
    [
        "CW8,2026-09-25,-1,EUR",  # prix négatif
        "CW8,25/09/2026,10,EUR",  # date invalide
        "CW8,2026-09-25,abc,EUR",
    ],
)
def test_bad_rows(line):
    with pytest.raises(PositionImportError):
        parse_price_csv(f"symbol,day,close,currency\n{line}\n", SRC)


def test_duplicates_and_credentials():
    with pytest.raises(PositionImportError, match="doublon"):
        parse_price_csv("symbol,day,close,currency\nA,2026-01-01,1,EUR\nA,2026-01-01,2,EUR\n", SRC)
    with pytest.raises(SensitiveDataError):
        parse_price_csv("symbol,day,close,currency,token\n", SRC)
