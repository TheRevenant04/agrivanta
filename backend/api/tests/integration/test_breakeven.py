import ast
import inspect
from decimal import Decimal

import pytest

from api import breakeven
from api.breakeven import BreakEvenError, calculate_break_even


def _data(**overrides):
    data = {
        "fixed_costs": Decimal("5000"),
        "variable_cost_per_unit": Decimal("6.00"),
        "selling_price_per_unit": Decimal("10.00"),
        "expected_yield": Decimal("2000"),
    }
    data.update(overrides)
    return data


def _calculate(**overrides):
    return calculate_break_even(_data(**overrides))


def test_module_has_no_framework_database_or_nondeterministic_imports():
    source = inspect.getsource(breakeven)
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
    assert issubclass(BreakEvenError, ValueError)


def test_known_input_break_even_quantity():
    result = _calculate()

    assert result["break_even_quantity"] == Decimal("1250")


def test_known_input_break_even_price():
    result = _calculate()

    assert result["break_even_price"] == Decimal("8.50")
    assert result["break_even_price"] == Decimal("8.5")


def test_known_input_contribution_margin():
    result = _calculate()

    assert result["contribution_margin"] == Decimal("4.00")


def test_known_input_returns_only_decimal_values():
    result = _calculate()

    assert set(result) == {
        "break_even_quantity",
        "break_even_price",
        "contribution_margin",
    }
    assert all(isinstance(value, Decimal) for value in result.values())


@pytest.mark.parametrize(
    "field",
    [
        "fixed_costs",
        "variable_cost_per_unit",
        "selling_price_per_unit",
        "expected_yield",
    ],
)
def test_missing_key_raises_naming_the_field(field):
    data = _data()
    del data[field]

    with pytest.raises(BreakEvenError, match=field):
        calculate_break_even(data)


@pytest.mark.parametrize(
    "field",
    [
        "fixed_costs",
        "variable_cost_per_unit",
        "selling_price_per_unit",
        "expected_yield",
    ],
)
def test_none_value_raises_naming_the_field(field):
    with pytest.raises(BreakEvenError, match=field):
        _calculate(**{field: None})


def test_missing_fixed_costs_is_never_treated_as_zero():
    data = _data()
    del data["fixed_costs"]

    with pytest.raises(BreakEvenError, match="fixed_costs"):
        calculate_break_even(data)


def test_missing_expected_yield_is_never_treated_as_zero():
    data = _data()
    del data["expected_yield"]

    with pytest.raises(BreakEvenError, match="expected_yield"):
        calculate_break_even(data)


def test_missing_selling_price_is_never_treated_as_zero():
    data = _data()
    del data["selling_price_per_unit"]

    with pytest.raises(BreakEvenError, match="selling_price_per_unit"):
        calculate_break_even(data)


def test_missing_variable_cost_per_unit_names_the_field():
    data = _data()
    del data["variable_cost_per_unit"]

    with pytest.raises(BreakEvenError, match="variable_cost_per_unit"):
        calculate_break_even(data)


def test_zero_contribution_margin_raises_clear_error():
    with pytest.raises(BreakEvenError, match="[Zz]ero contribution margin"):
        _calculate(
            selling_price_per_unit=Decimal("6.00"),
            variable_cost_per_unit=Decimal("6.00"),
        )


def test_negative_contribution_margin_states_assumptions_are_inconsistent():
    with pytest.raises(BreakEvenError, match="[Ii]nconsistent"):
        _calculate(
            selling_price_per_unit=Decimal("4.00"),
            variable_cost_per_unit=Decimal("6.00"),
        )


@pytest.mark.parametrize("expected_yield", [0, "0", Decimal("-1"), "-0.01"])
def test_expected_yield_not_positive_raises_naming_the_field(expected_yield):
    with pytest.raises(BreakEvenError, match="expected_yield"):
        _calculate(expected_yield=expected_yield)


@pytest.mark.parametrize(
    "field",
    ["fixed_costs", "variable_cost_per_unit", "selling_price_per_unit"],
)
def test_negative_cost_or_price_raises_naming_the_field(field):
    with pytest.raises(BreakEvenError, match=field):
        _calculate(**{field: Decimal("-1")})


def test_accepts_int_str_and_decimal_inputs():
    result = calculate_break_even(
        {
            "fixed_costs": 5000,
            "variable_cost_per_unit": "6.00",
            "selling_price_per_unit": Decimal("10.00"),
            "expected_yield": "2000",
        }
    )

    assert result["break_even_quantity"] == Decimal("1250")
    assert result["break_even_price"] == Decimal("8.5")
    assert result["contribution_margin"] == Decimal("4")
    assert all(isinstance(value, Decimal) for value in result.values())


def test_decimal_results_are_exact_without_float_artifacts():
    result = calculate_break_even(
        {
            "fixed_costs": Decimal("0.3"),
            "variable_cost_per_unit": Decimal("0.1"),
            "selling_price_per_unit": Decimal("0.3"),
            "expected_yield": Decimal("0.3"),
        }
    )

    assert result["contribution_margin"] == Decimal("0.2")
    assert str(result["contribution_margin"]) == "0.2"
    assert result["break_even_quantity"] == Decimal("1.5")
    assert str(result["break_even_quantity"]) == "1.5"
    assert result["break_even_price"] == Decimal("1.1")
    assert str(result["break_even_price"]) == "1.1"


def test_non_numeric_value_raises_naming_the_field():
    with pytest.raises(BreakEvenError, match="fixed_costs"):
        _calculate(fixed_costs="not-a-number")


def test_repeated_calls_are_deterministic():
    data = _data()

    first = calculate_break_even(data)
    second = calculate_break_even(data)
    third = calculate_break_even(data)

    assert first == second == third
    assert list(first.keys()) == list(second.keys())
    assert first["break_even_quantity"] == Decimal("1250")
    assert first["break_even_price"] == Decimal("8.5")
