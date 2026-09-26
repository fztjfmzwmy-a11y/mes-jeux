import pytest

from ai_investor.core.errors import ForbiddenActionError, PermissionDeniedError
from ai_investor.security.permissions import (
    AGENT_PERMISSIONS,
    FORBIDDEN_ACTIONS,
    AgentRole,
    Permission,
    parse_permission,
    parse_permissions,
    require,
)


def test_forbidden_actions_are_not_grantable_permissions():
    assert {p.value for p in Permission}.isdisjoint(FORBIDDEN_ACTIONS)


@pytest.mark.parametrize(
    "name",
    [
        "PLACE_ORDER",
        "place_order",
        "Place Order",
        "TRANSFER_MONEY",
        "withdraw-money",
        "CHANGE_ACCOUNT_SETTINGS",
        "  place_order  ",
    ],
)
def test_forbidden_actions_are_refused(name):
    with pytest.raises(ForbiddenActionError):
        parse_permission(name)


def test_forbidden_action_in_list_rejects_whole_list():
    with pytest.raises(ForbiddenActionError):
        parse_permissions(["READ_MARKET", "PLACE_ORDER"])


def test_unknown_permission_is_refused():
    with pytest.raises(PermissionDeniedError):
        parse_permission("SUPER_ADMIN")


def test_every_role_has_permissions_and_none_forbidden():
    assert set(AGENT_PERMISSIONS) == set(AgentRole)
    for perms in AGENT_PERMISSIONS.values():
        assert perms
        assert all(isinstance(p, Permission) for p in perms)


def test_permissions_mapping_is_immutable():
    with pytest.raises(TypeError):
        AGENT_PERMISSIONS[AgentRole.NEWS] = frozenset(Permission)  # type: ignore[index]


def test_least_privilege_news_agent_cannot_read_portfolio():
    with pytest.raises(PermissionDeniedError):
        require(AgentRole.NEWS, Permission.READ_PORTFOLIO)
    assert require(AgentRole.NEWS, "READ_NEWS") is Permission.READ_NEWS


@pytest.mark.parametrize("role", list(AgentRole))
def test_no_agent_can_place_order_even_if_asked(role):
    for action in FORBIDDEN_ACTIONS:
        with pytest.raises(ForbiddenActionError):
            require(role, action)
