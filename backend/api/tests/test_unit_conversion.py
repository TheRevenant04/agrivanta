from decimal import Decimal

import pytest

from api.unit_conversion import (
    ConversionRuleData,
    IncompatibleUnitsError,
    InvalidConversionFactorError,
    MissingConversionRuleError,
    UnitData,
    conversion_factor,
    convert_quantity,
)


KG = UnitData("kg", "kg", "mass")
GRAM = UnitData("g", "g", "mass")
LITRE = UnitData("l", "L", "volume")
KG_TO_GRAM = ConversionRuleData("kg", "g", Decimal("1000"))


def test_convert_quantity_applies_direct_rule():
    assert convert_quantity(Decimal("2"), KG, GRAM, [KG_TO_GRAM]) == Decimal(
        "2000"
    )
    assert conversion_factor(KG, GRAM, [KG_TO_GRAM]) == Decimal("1000")


def test_convert_quantity_uses_inverse_rule():
    assert convert_quantity(Decimal("500"), GRAM, KG, [KG_TO_GRAM]) == Decimal(
        "0.5"
    )
    assert conversion_factor(GRAM, KG, [KG_TO_GRAM]) == Decimal("0.001")


def test_convert_quantity_returns_same_unit_without_a_rule():
    quantity = Decimal("12.50")

    assert convert_quantity(quantity, KG, KG, []) is quantity
    assert conversion_factor(KG, KG, []) == Decimal(1)


def test_convert_quantity_handles_zero_with_a_valid_rule():
    assert convert_quantity(Decimal(0), KG, GRAM, [KG_TO_GRAM]) == Decimal(0)


def test_convert_quantity_rejects_incompatible_base_measures():
    with pytest.raises(IncompatibleUnitsError, match="base measures do not match"):
        convert_quantity(Decimal(1), KG, LITRE, [])


def test_convert_quantity_rejects_missing_rule_with_unit_names():
    with pytest.raises(
        MissingConversionRuleError, match='from "kg" to "g"'
    ):
        convert_quantity(Decimal(1), KG, GRAM, [])


@pytest.mark.parametrize(
    "factor",
    [
        Decimal(0),
        Decimal("-1"),
        Decimal("NaN"),
        Decimal("Infinity"),
        "not-a-number",
    ],
)
def test_convert_quantity_rejects_invalid_conversion_factors(factor):
    invalid_rule = ConversionRuleData("kg", "g", factor)

    with pytest.raises(InvalidConversionFactorError, match="finite positive"):
        convert_quantity(Decimal(1), KG, GRAM, [invalid_rule])
