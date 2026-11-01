import ast
import inspect
from decimal import Decimal

import pytest

from api import profitability
from api.profitability import (
    ProfitabilityError,
    calculate_crop_cycle_profitability,
)


def _data(**overrides):
    data = {
        "revenue": Decimal("10000.00"),
        "direct_costs": [Decimal("7500.00")],
        "allocated_overheads": [],
    }
    data.update(overrides)
    return data


def _calculate(**overrides):
    return calculate_crop_cycle_profitability(_data(**overrides))


def test_module_has_no_framework_database_or_nondeterministic_imports():
    source = inspect.getsource(profitability)
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


def test_known_input_operating_surplus():
    result = _calculate()

    assert result["revenue"] == Decimal("10000.00")
    assert result["direct_costs"] == Decimal("7500.00")
    assert result["operating_surplus"] == Decimal("2500.00")


def test_known_input_result_after_allocated_overheads():
    result = _calculate(allocated_overheads=[Decimal("500.00")])

    assert result["operating_surplus"] == Decimal("2500.00")
    assert result["allocated_overheads"] == Decimal("500.00")
    assert result["result_after_allocated_overheads"] == Decimal("2000.00")


@pytest.mark.parametrize(
    "field", ["revenue", "direct_costs", "allocated_overheads"]
)
def test_missing_key_raises_naming_the_field(field):
    data = _data()
    del data[field]

    with pytest.raises(ProfitabilityError, match=field):
        calculate_crop_cycle_profitability(data)


@pytest.mark.parametrize(
    "field", ["revenue", "direct_costs", "allocated_overheads"]
)
def test_none_value_raises_naming_the_field(field):
    with pytest.raises(ProfitabilityError, match=field):
        _calculate(**{field: None})


def test_empty_direct_costs_is_valid_and_sums_to_zero():
    result = _calculate(direct_costs=[])

    assert result["direct_costs"] == Decimal("0")
    assert result["operating_surplus"] == result["revenue"]


def test_empty_allocated_overheads_is_valid_and_sums_to_zero():
    result = _calculate(allocated_overheads=[])

    assert result["allocated_overheads"] == Decimal("0")
    assert (
        result["result_after_allocated_overheads"]
        == result["operating_surplus"]
    )


@pytest.mark.parametrize("field", ["direct_costs", "allocated_overheads"])
def test_scalar_instead_of_collection_raises_naming_the_field(field):
    with pytest.raises(ProfitabilityError, match=field):
        _calculate(**{field: Decimal("100")})


def test_loss_making_cycle_returns_negative_values():
    result = _calculate(
        revenue=Decimal("1000.00"),
        direct_costs=[Decimal("1500.00")],
        allocated_overheads=[Decimal("100.00")],
    )

    assert result["operating_surplus"] == Decimal("-500.00")
    assert result["result_after_allocated_overheads"] == Decimal("-600.00")
    assert result["operating_surplus"] < 0
    assert result["result_after_allocated_overheads"] < 0


def test_decimal_sums_are_exact_without_float_artifacts():
    result = calculate_crop_cycle_profitability(
        {
            "revenue": Decimal("1.0"),
            "direct_costs": [Decimal("0.1"), Decimal("0.2")],
            "allocated_overheads": [],
        }
    )

    assert result["direct_costs"] == Decimal("0.3")
    assert str(result["direct_costs"]) == "0.3"
    assert result["operating_surplus"] == Decimal("0.7")
    assert str(result["operating_surplus"]) == "0.7"


def test_decimal_cancellation_is_exact():
    result = calculate_crop_cycle_profitability(
        {
            "revenue": Decimal("0.3"),
            "direct_costs": [Decimal("0.1"), Decimal("0.2")],
            "allocated_overheads": [],
        }
    )

    assert result["operating_surplus"] == Decimal("0")


def test_accepts_int_str_and_decimal_inputs():
    result = calculate_crop_cycle_profitability(
        {
            "revenue": 10000,
            "direct_costs": ["2500", Decimal("5000")],
            "allocated_overheads": [500],
        }
    )

    assert result["revenue"] == Decimal("10000")
    assert result["direct_costs"] == Decimal("7500")
    assert result["allocated_overheads"] == Decimal("500")
    assert result["operating_surplus"] == Decimal("2500")
    assert result["result_after_allocated_overheads"] == Decimal("2000")
    assert all(isinstance(value, Decimal) for value in result.values())


def test_non_numeric_value_raises_naming_the_field():
    with pytest.raises(ProfitabilityError, match="revenue"):
        _calculate(revenue="not-a-number")


def test_repeated_calls_are_deterministic():
    data = _data(
        direct_costs=[Decimal("7000.00"), Decimal("500.00")],
        allocated_overheads=[Decimal("500.00")],
    )

    first = calculate_crop_cycle_profitability(data)
    second = calculate_crop_cycle_profitability(data)

    assert first == second
    assert list(first.keys()) == list(second.keys())
    assert first["operating_surplus"] == Decimal("2500.00")
    assert first["result_after_allocated_overheads"] == Decimal("2000.00")
