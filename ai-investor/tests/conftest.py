from datetime import UTC, datetime

import pytest

from ai_investor.core.enums import DataReliability
from ai_investor.core.provenance import Source

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


@pytest.fixture
def now() -> datetime:
    return NOW


@pytest.fixture
def source() -> Source:
    return Source(name="fichier-test.csv", reliability=DataReliability.SIMULATED)
