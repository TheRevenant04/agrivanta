from dataclasses import dataclass
from decimal import Decimal, DecimalException, InvalidOperation
from typing import Hashable, Iterable


class UnitConversionError(ValueError):
    pass


class IncompatibleUnitsError(UnitConversionError):
    pass


class MissingConversionRuleError(UnitConversionError):
    pass


class InvalidConversionFactorError(UnitConversionError):
    pass


@dataclass(frozen=True)
class UnitData:
    id: Hashable
    name: str
    base_measure: str


@dataclass(frozen=True)
class ConversionRuleData:
    from_unit_id: Hashable
    to_unit_id: Hashable
    factor: Decimal | str


def _matching_rule(
    from_unit: UnitData,
    to_unit: UnitData,
    rules: Iterable[ConversionRuleData],
) -> tuple[ConversionRuleData | None, bool]:
    if from_unit.id == to_unit.id:
        return None, False
    if from_unit.base_measure != to_unit.base_measure:
        raise IncompatibleUnitsError(
            f'Cannot convert "{from_unit.name}" '
            f"({from_unit.base_measure}) to \"{to_unit.name}\" "
            f"({to_unit.base_measure}): base measures do not match."
        )

    rules = tuple(rules)
    for rule in rules:
        if rule.from_unit_id == from_unit.id and rule.to_unit_id == to_unit.id:
            return rule, False
    for rule in rules:
        if rule.from_unit_id == to_unit.id and rule.to_unit_id == from_unit.id:
            return rule, True
    raise MissingConversionRuleError(
        f'No rule exists for converting from "{from_unit.name}" '
        f'to "{to_unit.name}".'
    )


def _validated_factor(rule: ConversionRuleData) -> Decimal:
    try:
        factor = (
            rule.factor
            if isinstance(rule.factor, Decimal)
            else Decimal(str(rule.factor))
        )
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidConversionFactorError(
            "Conversion factor must be a finite positive number."
        ) from exc
    if not factor.is_finite() or factor <= 0:
        raise InvalidConversionFactorError(
            "Conversion factor must be a finite positive number."
        )
    return factor


def conversion_factor(
    from_unit: UnitData,
    to_unit: UnitData,
    rules: Iterable[ConversionRuleData],
) -> Decimal:
    rule, is_inverse = _matching_rule(from_unit, to_unit, rules)
    if rule is None:
        return Decimal(1)
    factor = _validated_factor(rule)
    if is_inverse:
        try:
            factor = Decimal(1) / factor
        except DecimalException as exc:
            raise InvalidConversionFactorError(
                "Conversion factor must be a finite positive number."
            ) from exc
        if not factor.is_finite() or factor <= 0:
            raise InvalidConversionFactorError(
                "Conversion factor must be a finite positive number."
            )
    return factor


def convert_quantity(
    quantity: Decimal,
    from_unit: UnitData,
    to_unit: UnitData,
    rules: Iterable[ConversionRuleData],
) -> Decimal:
    rule, is_inverse = _matching_rule(from_unit, to_unit, rules)
    if rule is None:
        return quantity
    factor = _validated_factor(rule)
    try:
        return quantity / factor if is_inverse else quantity * factor
    except DecimalException as exc:
        raise InvalidConversionFactorError(
            "Conversion factor must be a finite positive number."
        ) from exc
