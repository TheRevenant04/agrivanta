import ast
import inspect
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from api import allocation
from api.allocation import AllocationError, allocate_shared_cost
from api.models import AllocationBasis, AllocationRule, Farm


def _targets(*areas, **extra):
    targets = [
        {"id": f"target-{index}", "area": area}
        for index, area in enumerate(areas)
    ]
    for target in targets:
        target.update(extra)
    return targets


def _sum_amounts(result):
    return sum((entry["amount"] for entry in result), Decimal(0))


def test_module_has_no_framework_database_or_nondeterministic_imports():
    source = inspect.getsource(allocation)
    tree = ast.parse(source)

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    forbidden_roots = (
        "django",
        "rest_framework",
        "random",
        "secrets",
        "datetime",
        "time",
        "api.models",
    )
    for name in imported:
        assert not any(
            name == root or name.startswith(f"{root}.")
            for root in forbidden_roots
        ), f"forbidden import: {name}"

    assert "django" not in source.lower()
    assert "rest_framework" not in source.lower()


def test_error_is_a_value_error_subclass():
    assert issubclass(AllocationError, ValueError)


def test_per_hectare_allocates_proportionally_to_area():
    result = allocate_shared_cost(
        Decimal("1200"),
        [
            {"id": "north", "area": "10"},
            {"id": "south", "area": "30"},
            {"id": "east", "area": "20"},
        ],
        "per_hectare",
    )

    assert result == [
        {"id": "north", "amount": Decimal("200.0000")},
        {"id": "south", "amount": Decimal("600.0000")},
        {"id": "east", "amount": Decimal("400.0000")},
    ]


def test_per_hectare_preserves_input_order_and_ignores_extra_keys():
    result = allocate_shared_cost(
        "100",
        [
            {"id": "b", "area": "3", "extra": "ignored"},
            {"id": "a", "area": "1"},
        ],
        "per_hectare",
    )

    assert [entry["id"] for entry in result] == ["b", "a"]
    assert [entry["amount"] for entry in result] == [
        Decimal("75.0000"),
        Decimal("25.0000"),
    ]


def test_per_cycle_share_splits_cost_equally_and_ignores_area():
    result = allocate_shared_cost(
        100,
        _targets("1", "1000", "0"),
        "per_cycle_share",
    )

    assert result == [
        {"id": "target-0", "amount": Decimal("33.3333")},
        {"id": "target-1", "amount": Decimal("33.3333")},
        {"id": "target-2", "amount": Decimal("33.3334")},
    ]
    assert _sum_amounts(result) == Decimal("100")


def test_per_cycle_share_known_exact_split():
    result = allocate_shared_cost(
        Decimal("1200"),
        _targets("1", "2", "3", "4"),
        "per_cycle_share",
    )

    assert [entry["amount"] for entry in result] == [
        Decimal("300.0000"),
        Decimal("300.0000"),
        Decimal("300.0000"),
        Decimal("300.0000"),
    ]


@pytest.mark.parametrize("basis", ["per_hectare", "per_cycle_share"])
def test_single_target_receives_the_whole_cost(basis):
    result = allocate_shared_cost(
        Decimal("123.4567"),
        [{"id": "only", "area": "5"}],
        basis,
    )

    assert result == [{"id": "only", "amount": Decimal("123.4567")}]


def test_zero_area_target_receives_zero():
    result = allocate_shared_cost(
        Decimal("100"),
        _targets("40", "0", "60"),
        "per_hectare",
    )

    assert [entry["amount"] for entry in result] == [
        Decimal("40.0000"),
        Decimal("0.0000"),
        Decimal("60.0000"),
    ]


def test_rounding_remainder_never_goes_to_a_zero_area_target():
    result = allocate_shared_cost(
        Decimal("100"),
        _targets("1", "1", "1", "0"),
        "per_hectare",
    )

    assert [entry["amount"] for entry in result] == [
        Decimal("33.3333"),
        Decimal("33.3333"),
        Decimal("33.3334"),
        Decimal("0.0000"),
    ]
    assert _sum_amounts(result) == Decimal("100")


def test_exact_decimal_sum_for_repeating_division():
    result = allocate_shared_cost(
        Decimal("100"),
        _targets("1", "1", "1"),
        "per_hectare",
    )

    assert _sum_amounts(result) == Decimal("100")
    assert all(
        entry["amount"].as_tuple().exponent == -4 for entry in result
    )


def test_zero_cost_returns_zero_amounts():
    result = allocate_shared_cost(
        0,
        _targets("1", "2"),
        "per_cycle_share",
    )

    assert [entry["amount"] for entry in result] == [
        Decimal("0.0000"),
        Decimal("0.0000"),
    ]


def test_empty_targets_raise_for_every_basis():
    for basis in ("per_hectare", "per_cycle_share"):
        with pytest.raises(AllocationError, match="empty"):
            allocate_shared_cost(Decimal("10"), [], basis)


def test_all_zero_area_targets_raise():
    with pytest.raises(AllocationError, match="area"):
        allocate_shared_cost(
            Decimal("10"),
            _targets("0", "0"),
            "per_hectare",
        )


def test_unknown_basis_raises_a_clear_error():
    with pytest.raises(AllocationError, match="basis"):
        allocate_shared_cost(Decimal("10"), _targets("1"), "per_acre")


def test_targets_must_be_a_collection_of_mappings_with_ids():
    with pytest.raises(AllocationError, match="list or tuple"):
        allocate_shared_cost(Decimal("10"), {"id": "a", "area": "1"}, "per_hectare")

    with pytest.raises(AllocationError, match="mapping"):
        allocate_shared_cost(Decimal("10"), ["not-a-target"], "per_hectare")

    with pytest.raises(AllocationError, match="id"):
        allocate_shared_cost(
            Decimal("10"), [{"area": "1"}], "per_hectare"
        )


def test_missing_area_raises_naming_the_target():
    with pytest.raises(AllocationError, match="area"):
        allocate_shared_cost(
            Decimal("10"), [{"id": "no-area"}], "per_hectare"
        )


@pytest.mark.parametrize(
    "cost",
    [
        -1,
        "-0.01",
        "not-a-number",
        None,
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_invalid_or_negative_cost_raises(cost):
    with pytest.raises(AllocationError, match="cost"):
        allocate_shared_cost(cost, _targets("1"), "per_hectare")


@pytest.mark.parametrize(
    "area",
    [
        -1,
        "-0.01",
        "not-a-number",
        None,
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_invalid_or_negative_area_raises(area):
    with pytest.raises(AllocationError, match="area"):
        allocate_shared_cost(
            Decimal("10"),
            [{"id": "bad", "area": area}],
            "per_hectare",
        )


def test_accepts_int_str_and_decimal_inputs():
    result = allocate_shared_cost(
        100,
        [
            {"id": "a", "area": "1"},
            {"id": "b", "area": Decimal("3")},
        ],
        "per_hectare",
    )

    assert [entry["amount"] for entry in result] == [
        Decimal("25.0000"),
        Decimal("75.0000"),
    ]


def test_repeated_calls_are_deterministic_and_do_not_mutate_input():
    targets = [
        {"id": "a", "area": "1"},
        {"id": "b", "area": "2"},
        {"id": "c", "area": "4"},
    ]
    snapshot = [dict(target) for target in targets]

    first = allocate_shared_cost(Decimal("100"), targets, "per_hectare")
    second = allocate_shared_cost(Decimal("100"), targets, "per_hectare")

    assert first == second
    assert targets == snapshot


def _farm(session):
    return Farm.objects.get(owner_id=session["user"]["id"])


def test_allocation_rule_persists_with_defaults(session):
    farm = _farm(session)
    rule = AllocationRule.objects.create(
        farm=farm,
        name="Split overheads equally",
        basis=AllocationBasis.PER_CYCLE_SHARE,
    )

    assert rule.id is not None
    assert rule.parameters == {}
    assert rule.active_from is None
    assert rule.active_to is None
    assert rule.created_at is not None
    assert rule.updated_at is not None
    assert list(farm.allocation_rules.all()) == [rule]
    assert list(
        AllocationRule.objects.filter(farm=farm)
    ) == [rule]


def test_allocation_rule_active_period_is_validated_by_clean(session):
    farm = _farm(session)
    rule = AllocationRule(
        farm=farm,
        name="Backwards period",
        basis=AllocationBasis.PER_HECTARE,
        parameters={"include_fallow": False},
        active_from=date(2026, 5, 1),
        active_to=date(2026, 4, 30),
    )

    with pytest.raises(ValidationError) as excinfo:
        rule.full_clean()

    assert "active_to" in excinfo.value.message_dict


def test_allocation_rule_active_period_is_enforced_by_the_database(session):
    farm = _farm(session)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            AllocationRule.objects.create(
                farm=farm,
                name="Backwards period",
                basis=AllocationBasis.PER_HECTARE,
                active_from=date(2026, 5, 1),
                active_to=date(2026, 4, 30),
            )


def test_allocation_rule_accepts_open_and_single_day_periods(session):
    farm = _farm(session)
    open_start = AllocationRule(
        farm=farm,
        name="Open start",
        basis=AllocationBasis.PER_HECTARE,
        active_to=date(2026, 4, 30),
    )
    open_end = AllocationRule(
        farm=farm,
        name="Open end",
        basis=AllocationBasis.PER_CYCLE_SHARE,
        active_from=date(2026, 5, 1),
    )
    single_day = AllocationRule(
        farm=farm,
        name="Single day",
        basis=AllocationBasis.PER_HECTARE,
        active_from=date(2026, 5, 1),
        active_to=date(2026, 5, 1),
    )

    for rule in (open_start, open_end, single_day):
        rule.full_clean()
        rule.save()

    assert farm.allocation_rules.count() == 3
