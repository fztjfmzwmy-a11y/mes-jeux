import pytest

from ai_investor.core.errors import SensitiveDataError
from ai_investor.security.secrets_guard import (
    assert_no_sensitive_columns,
    assert_no_sensitive_fields,
    find_sensitive_fields,
    is_sensitive_field,
)


@pytest.mark.parametrize(
    "field",
    [
        "password",
        "Passwort",
        "PIN",
        "pin_code",
        "2fa",
        "otp",
        "sessionToken",
        "session_id",
        "cookie",
        "Authorization",
        "api_key",
        "apiKey",
        "IBAN",
        "mot_de_passe",
        "accessToken",
        "tr_refresh_token",
        "card-number",
    ],
)
def test_sensitive_fields_detected(field):
    assert is_sensitive_field(field)


@pytest.mark.parametrize(
    "field",
    [
        "isin",
        "symbol",
        "quantity",
        "average_price",
        "shipping",
        "opinion",
        "spinoff",
        "currency",
        "date",
        "sector",
        "name",
        "stand",
    ],
)
def test_normal_fields_not_flagged(field):
    assert not is_sensitive_field(field)


def test_nested_structures_are_scanned():
    data = {"positions": [{"isin": "X"}, {"isin": "Y", "meta": {"pin": "1234"}}]}
    assert find_sensitive_fields(data) == ["positions[1].meta.pin"]


def test_import_with_credentials_is_refused_without_leaking_value():
    with pytest.raises(SensitiveDataError) as exc:
        assert_no_sensitive_fields({"isin": "US0378331005", "password": "hunter2"})
    assert "hunter2" not in str(exc.value)
    assert "password" in str(exc.value)


def test_csv_columns_checked():
    assert_no_sensitive_columns(["isin", "quantity", "price"])
    with pytest.raises(SensitiveDataError):
        assert_no_sensitive_columns(["isin", "Session Cookie"])
